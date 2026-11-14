import socket
import os
import struct
import sys
import hashlib

SERVER_PORT = 5001
CHUNK_SIZE = 1024 * 1024

BACKUP_SERVERS = [
    "10.0.0.3",
    "10.0.0.4"
]

CONNECTION_TIMEOUT = 10


def calculate_hash(data):
    return hashlib.sha256(data).digest()


def receive_exact(sock, size):
    data = b''

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError("Connection interrupted")

        data += chunk

    return data


def connect_to_server(server_host=None):

    servers = [server_host] if server_host else BACKUP_SERVERS

    for host in servers:

        client = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        client.settimeout(CONNECTION_TIMEOUT)

        try:
            print(f"Trying backup server: {host}")

            client.connect((host, SERVER_PORT))

            print(f"Connected to backup server: {host}")

            return client, host

        except OSError as e:

            print(f"Server {host} unavailable: {e}")
            client.close()

    raise ConnectionError("No backup servers are available")


def send_metadata(client, filename_bytes, file_size,
                  total_chunks, overall_hash):

    header = struct.pack(
        '!HQII',
        len(filename_bytes),
        file_size,
        CHUNK_SIZE,
        total_chunks
    )

    client.sendall(header)
    client.sendall(filename_bytes)
    client.sendall(overall_hash)


def receive_missing_chunks(client):

    missing_count = struct.unpack(
        '!I',
        receive_exact(client, 4)
    )[0]

    missing_chunks = []

    for _ in range(missing_count):

        sequence = struct.unpack(
            '!I',
            receive_exact(client, 4)
        )[0]

        missing_chunks.append(sequence)

    return missing_chunks


def receive_server_response(client):

    response_length = struct.unpack(
        '!I',
        receive_exact(client, 4)
    )[0]

    response = receive_exact(
        client,
        response_length
    ).decode()

    return response


def send_file(server_host, filepath, corrupt=False, interrupt=False):

    if not os.path.isfile(filepath):
        print("File not found!")
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    filename_bytes = filename.encode()

    total_chunks = (
        file_size + CHUNK_SIZE - 1
    ) // CHUNK_SIZE

    overall_hash = hashlib.sha256()

    # Calculate complete file hash
    with open(filepath, 'rb') as file:

        while True:
            data = file.read(4096)

            if not data:
                break

            overall_hash.update(data)

    original_hash = overall_hash.digest()

    # Determine server order
    if server_host:

        server_list = [server_host]

    else:

        server_list = BACKUP_SERVERS.copy()

    attempted_servers = set()

    # Track intentional demonstration modes
    interrupted_demo = False

    print("\nStarting distributed backup...")
    print(f"Filename: {filename}")
    print(f"File size: {file_size} bytes")
    print(f"Total chunks: {total_chunks}")

    # Try available backup servers
    while server_list:

        current_server = server_list.pop(0)

        if current_server in attempted_servers:
            continue

        attempted_servers.add(current_server)

        client = None

        try:

            # 1. Connect to selected server
            client, selected_server = connect_to_server(
                current_server
            )

            # 2. Send file metadata
            send_metadata(
                client,
                filename_bytes,
                file_size,
                total_chunks,
                original_hash
            )

            # 3. Receive missing chunks
            missing_chunks = receive_missing_chunks(client)

            print(f"\nSelected server: {selected_server}")

            print(f"Total chunks: {total_chunks}")

            print(
                f"Already backed up: "
                f"{total_chunks - len(missing_chunks)}"
            )

            print(
                f"Chunks remaining: {len(missing_chunks)}"
            )

            # 4. Send missing chunks
            with open(filepath, 'rb') as file:

                for position, sequence in enumerate(missing_chunks):

                    file.seek(sequence * CHUNK_SIZE)

                    data = file.read(CHUNK_SIZE)

                    chunk_hash = calculate_hash(data)

                    # Corruption demonstration
                    if corrupt and sequence == 2 and data:

                        data = b'X' + data[1:]

                        print(
                            "DEMO: Third chunk deliberately corrupted!"
                        )

                    chunk_header = struct.pack(
                        '!II',
                        sequence,
                        len(data)
                    )

                    client.sendall(chunk_header)
                    client.sendall(chunk_hash)
                    client.sendall(data)

                    print(
                        f"Sent chunk "
                        f"{sequence + 1}/{total_chunks}"
                    )

                    # Interrupted transfer demonstration
                    if interrupt and position == 1:

                        print(
                            "\nDEMO: Interrupting transfer "
                            "after 2 chunks!"
                        )

                        interrupted_demo = True

                        return

            # 5. Receive server response
            response = receive_server_response(client)

            print("\nServer response:", response)

            if response.startswith("SUCCESS"):

                print("\nTRANSFER SUCCESSFUL!")

                print("Selected server:", selected_server)
                print("Filename:", filename)
                print("File size:", file_size)

                print(
                    "Original SHA-256:",
                    overall_hash.hexdigest()
                )

                return

            else:

                print("\nTRANSFER REJECTED!")
                print("Server error:", response)

                return

        except (ConnectionError, OSError, socket.timeout) as e:

            print("\nTRANSFER CONNECTION FAILED!")
            print(f"Server: {current_server}")
            print(f"Reason: {e}")

            if server_list:

                print("\nINITIATING AUTOMATIC FAILOVER...")

                print(
                    f"Switching from {current_server} "
                    f"to {server_list[0]}"
                )

            else:

                print("\nALL BACKUP SERVERS FAILED.")

        finally:

            if client:
                client.close()

    if not interrupted_demo:

        print("\nBACKUP FAILED.")
        print("No available backup server could complete the transfer.")


if __name__ == "__main__":

    if len(sys.argv) < 3:

        print(
            "Usage:\n"
            "Explicit server: python3 backup_client.py "
            "<server_ip> <filepath> [--corrupt] [--interrupt]\n"
            "Automatic: python3 backup_client.py "
            "--auto <filepath> [--corrupt] [--interrupt]"
        )

        sys.exit(1)

    first_argument = sys.argv[1]

    if first_argument == "--auto":

        server_host = None
        filepath = sys.argv[2]
        options = sys.argv[3:]

    else:

        server_host = first_argument
        filepath = sys.argv[2]
        options = sys.argv[3:]

    if any(
        option not in ("--corrupt", "--interrupt")
        for option in options
    ):

        print("Invalid option.")
        sys.exit(1)

    corrupt_mode = "--corrupt" in options
    interrupt_mode = "--interrupt" in options

    send_file(
        server_host,
        filepath,
        corrupt=corrupt_mode,
        interrupt=interrupt_mode
    )
