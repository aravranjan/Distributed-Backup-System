import socket
import os
import struct
import sys
import hashlib

SERVER_PORT = 5001


def calculate_hash(filepath):

    sha256 = hashlib.sha256()

    with open(filepath, 'rb') as file:

        while True:
            data = file.read(4096)

            if not data:
                break

            sha256.update(data)

    return sha256.digest()


def send_file(server_host, filepath):

    if not os.path.isfile(filepath):
        print("File not found!")
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)

    # Calculate original file hash
    original_hash = calculate_hash(filepath)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((server_host, SERVER_PORT))

        filename_bytes = filename.encode()

        # Send filename length and file size
        header = struct.pack(
            '!HQ',
            len(filename_bytes),
            file_size
        )

        client.sendall(header)
        client.sendall(filename_bytes)

        # Send SHA-256 hash (32 bytes)
        client.sendall(original_hash)

        # Send file contents
        with open(filepath, 'rb') as file:

            while True:
                data = file.read(4096)

                if not data:
                    break

                client.sendall(data)

        # Receive server verification result
        response = client.recv(1024).decode()

        print(f"File sent: {filename}")
        print(f"Original SHA-256: {original_hash.hex()}")
        print(f"Server response: {response}")

    except Exception as e:
        print(f"Transfer failed: {e}")

    finally:
        client.close()


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage: python3 backup_client.py <server_ip> <filepath>")

    else:
        send_file(sys.argv[1], sys.argv[2])
