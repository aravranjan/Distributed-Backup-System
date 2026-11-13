import socket
import os
import struct

HOST = '0.0.0.0'
PORT = 5001

SAVE_DIR = 'backups'
os.makedirs(SAVE_DIR, exist_ok=True)


def receive_exact(conn, size):
    data = b''

    while len(data) < size:
        chunk = conn.recv(size - len(data))

        if not chunk:
            raise ConnectionError("Connection interrupted")

        data += chunk

    return data


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen(5)

print(f"Backup server listening on port {PORT}")

while True:

    conn, addr = server.accept()
    print(f"Connected to client: {addr}")

    try:
        # Receive filename length and file size
        header = receive_exact(conn, 10)

        filename_length, file_size = struct.unpack('!HQ', header)

        # Receive filename
        filename = receive_exact(conn, filename_length).decode()

        filename = os.path.basename(filename)
        filepath = os.path.join(SAVE_DIR, filename)

        received = 0

        with open(filepath, 'wb') as file:

            while received < file_size:

                chunk_size = min(4096, file_size - received)
                data = receive_exact(conn, chunk_size)

                file.write(data)
                received += len(data)

        print(f"Received: {filename}")
        print(f"Size: {received} bytes")

    except Exception as e:
        print(f"Transfer failed: {e}")

    finally:
        conn.close()

