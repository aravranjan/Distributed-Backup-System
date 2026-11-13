import socket
import os
import struct
import sys
import hashlib

SERVER_PORT = 5001
CHUNK_SIZE = 1024 * 1024  # 1 MB


def calculate_hash(data):
    return hashlib.sha256(data).digest()


def send_file(server_host, filepath, corrupt=False):

    if not os.path.isfile(filepath):
        print("File not found!")
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    filename_bytes = filename.encode()

    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    overall_hash = hashlib.sha256()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((server_host, SERVER_PORT))

        header = struct.pack(
            '!HQII',
            len(filename_bytes),
            file_size,
            CHUNK_SIZE,
            total_chunks
        )

        client.sendall(header)
        client.sendall(filename_bytes)

        # Calculate original file hash
        with open(filepath, 'rb') as file:
            while True:
                data = file.read(4096)
                if not data:
                    break
                overall_hash.update(data)

        client.sendall(overall_hash.digest())

        # Send chunks
        with open(filepath, 'rb') as file:

            for sequence in range(total_chunks):

                data = file.read(CHUNK_SIZE)

                # Calculate checksum BEFORE sending
                chunk_hash = calculate_hash(data)

                # Optional corruption demonstration
                if corrupt and sequence == 2 and data:
                    data = b'X' + data[1:]
                    print("DEMO: Third chunk deliberately corrupted!")

                chunk_header = struct.pack(
                    '!II', sequence, len(data)
                )

                client.sendall(chunk_header)
                client.sendall(chunk_hash)
                client.sendall(data)

                print(f"Sent chunk {sequence + 1}/{total_chunks}")

        response = client.recv(1024).decode()

        print("\nServer response:", response)

        if response.startswith("SUCCESS"):
            print("TRANSFER SUCCESSFUL!")
        else:
            print("TRANSFER REJECTED!")

        print("Filename:", filename)
        print("File size:", file_size, "bytes")
        print("Total chunks:", total_chunks)
        print("Original SHA-256:", overall_hash.hexdigest())

    except Exception as e:
        print("Transfer failed:", e)

    finally:
        client.close()


if __name__ == "__main__":

    if len(sys.argv) not in (3, 4):
        print(
            "Usage: python3 backup_client.py "
            "<server_ip> <filepath> [--corrupt]"
        )
        sys.exit(1)

    if len(sys.argv) == 4 and sys.argv[3] != "--corrupt":
        print("Invalid option. Use --corrupt for corruption testing.")
        sys.exit(1)

    corrupt_mode = len(sys.argv) == 4

    send_file(
        sys.argv[1],
        sys.argv[2],
        corrupt=corrupt_mode
    )
