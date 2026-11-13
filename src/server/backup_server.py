import socket
import os
import struct
import hashlib

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

server.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

server.bind((HOST, PORT))
server.listen(5)

print(f"Backup Server listening on port {PORT}")


while True:

    conn, addr = server.accept()

    print(f"\nConnected to client: {addr}")

    try:

        # Receive metadata
        header = receive_exact(conn, 10)

        filename_length, file_size = struct.unpack(
            '!HQ', header
        )

        # Receive filename
        filename = receive_exact(
            conn, filename_length
        ).decode()

        filename = os.path.basename(filename)

        # Receive original SHA-256 hash
        original_hash = receive_exact(conn, 32)

        filepath = os.path.join(SAVE_DIR, filename)

        # Calculate received file hash
        sha256 = hashlib.sha256()

        received = 0

        with open(filepath, 'wb') as file:

            while received < file_size:

                chunk_size = min(
                    4096,
                    file_size - received
                )

                data = receive_exact(conn, chunk_size)

                file.write(data)
                sha256.update(data)

                received += len(data)

        received_hash = sha256.digest()

        print(f"Received file: {filename}")
        print(f"Original SHA-256: {original_hash.hex()}")
        print(f"Received SHA-256: {received_hash.hex()}")

        # Compare hashes
        if original_hash == received_hash:

            print("INTEGRITY VERIFIED")

            conn.sendall(
                b"SUCCESS: SHA-256 hashes match"
            )

        else:

            print("INTEGRITY CHECK FAILED")

            os.remove(filepath)

            conn.sendall(
                b"ERROR: SHA-256 hashes do not match"
            )

    except Exception as e:

        print(f"Transfer failed: {e}")

    finally:

        conn.close()
