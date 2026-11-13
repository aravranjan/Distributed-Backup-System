import socket
import os
import struct
import sys

SERVER_PORT = 5001


def send_file(server_host, filepath):

    if not os.path.isfile(filepath):
        print(f"File not found: {filepath}")
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((server_host, SERVER_PORT))

        filename_bytes = filename.encode()

        header = struct.pack(
            '!HQ',
            len(filename_bytes),
            file_size
        )

        client.sendall(header)
        client.sendall(filename_bytes)

        with open(filepath, 'rb') as file:

            while True:
                data = file.read(4096)

                if not data:
                    break

                client.sendall(data)

        print(f"File sent successfully: {filename}")
        print(f"Size: {file_size} bytes")

    except Exception as e:
        print(f"Transfer failed: {e}")

    finally:
        client.close()


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage: python3 backup_client.py <server_ip> <filepath>")
    else:
        send_file(sys.argv[1], sys.argv[2])
