
import socket
import os
import struct
import sys
import hashlib

SERVER_PORT = 5001
CHUNK_SIZE = 1024 * 1024


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


def send_file(server_host, filepath, corrupt=False, interrupt=False):

    if not os.path.isfile(filepath):
        print("File not found!")
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    filename_bytes = filename.encode()

    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

    overall_hash = hashlib.sha256()

    # Calculate complete file hash
    with open(filepath, 'rb') as file:
        while True:
            data = file.read(4096)

            if not data:
                break

            overall_hash.update(data)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((server_host, SERVER_PORT))

        # 1. Send file metadata
        header = struct.pack(
            '!HQII',
            len(filename_bytes),
            file_size,
            CHUNK_SIZE,
            total_chunks
        )

        client.sendall(header)
        client.sendall(filename_bytes)
        client.sendall(overall_hash.digest())

        # 2. Receive missing chunk list from server
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

        print(f"\nTotal chunks: {total_chunks}")
        print(f"Already backed up: {total_chunks - missing_count}")
        print(f"Chunks remaining: {missing_count}")

        if missing_count == 0:
            print("All chunks already exist on server.")

        # 3. Send only missing chunks
        with open(filepath, 'rb') as file:

            for sequence in missing_chunks:

                file.seek(sequence * CHUNK_SIZE)
                data = file.read(CHUNK_SIZE)

                # Calculate checksum before sending
                chunk_hash = calculate_hash(data)

                # Corruption demonstration
                if corrupt and sequence == 2 and data:
                    data = b'X' + data[1:]
                    print("DEMO: Third chunk deliberately corrupted!")

                chunk_header = struct.pack(
                    '!II',
                    sequence,
                    len(data)
                )

                client.sendall(chunk_header)
                client.sendall(chunk_hash)
                client.sendall(data)

                print(
                    f"Sent chunk {sequence + 1}/{total_chunks}"
                )

                # Interrupt demonstration
                if interrupt and missing_chunks.index(sequence) == 1:
                    print("\nDEMO: Interrupting transfer after 2 chunks!")
                    return

        # 4. Receive server response
        response_length = struct.unpack(
            '!I',
            receive_exact(client, 4)
        )[0]

        response = receive_exact(
            client,
            response_length
        ).decode()

        print("\nServer response:", response)

        if response.startswith("SUCCESS"):
            print("TRANSFER SUCCESSFUL!")
        else:
            print("TRANSFER REJECTED!")

        print("Filename:", filename)
        print("File size:", file_size)
        print("Original SHA-256:", overall_hash.hexdigest())

    except Exception as e:
        print("\nTransfer failed:", e)

    finally:
        client.close()


if __name__ == "__main__":

    if len(sys.argv) < 3:
        print(
            "Usage: python3 backup_client.py "
            "<server_ip> <filepath> [--corrupt] [--interrupt]"
        )
        sys.exit(1)

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
        sys.argv[1],
        sys.argv[2],
        corrupt=corrupt_mode,
        interrupt=interrupt_mode
    )

