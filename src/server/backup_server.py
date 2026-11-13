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
            raise ConnectionError(
                "Connection interrupted"
            )

        data += chunk

    return data


server = socket.socket(
    socket.AF_INET,
    socket.SOCK_STREAM
)

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

    filepath = None

    try:

        # Receive metadata
        header = receive_exact(conn, 18)

        filename_length, file_size, chunk_size, total_chunks = (
            struct.unpack('!HQII', header)
        )

        if filename_length == 0 or filename_length > 255:
            raise ValueError("Invalid filename length")

        if chunk_size != 1024 * 1024:
            raise ValueError("Unexpected chunk size")

        expected_chunks = (
            file_size + chunk_size - 1
        ) // chunk_size

        if total_chunks != expected_chunks:
            raise ValueError("Invalid chunk count")

        filename = receive_exact(
            conn, filename_length
        ).decode()

        filename = os.path.basename(filename)

        if not filename:
            raise ValueError("Invalid filename")

        original_hash = receive_exact(conn, 32)

        filepath = os.path.join(
            SAVE_DIR,
            filename + '.part'
        )

        received_hash = hashlib.sha256()
        received_bytes = 0

        with open(filepath, 'wb') as file:

            for expected_sequence in range(total_chunks):

                # Receive chunk metadata
                chunk_header = receive_exact(conn, 8)

                sequence, chunk_length = struct.unpack(
                    '!II', chunk_header
                )

                expected_length = min(
                    chunk_size,
                    file_size - received_bytes
                )

                if sequence != expected_sequence:
                    raise ValueError("Invalid chunk sequence")

                if chunk_length != expected_length:
                    raise ValueError("Invalid chunk length")

                chunk_hash = receive_exact(conn, 32)

                chunk_data = receive_exact(
                    conn, chunk_length
                )

                calculated_hash = hashlib.sha256(
                    chunk_data
                ).digest()

                if calculated_hash != chunk_hash:
                    raise ValueError(
                        f"Chunk {sequence} checksum failed"
                    )

                file.write(chunk_data)
                received_hash.update(chunk_data)

                received_bytes += chunk_length

                print(
                    f"Verified chunk "
                    f"{sequence + 1}/{total_chunks}"
                )

        # Verify complete file
        if received_bytes != file_size:
            raise ValueError("File size mismatch")

        if received_hash.digest() != original_hash:
            raise ValueError("Overall SHA-256 mismatch")

        final_path = os.path.join(
            SAVE_DIR,
            filename
        )

        os.replace(filepath, final_path)

        filepath = None

        print(f"File received successfully: {filename}")
        print("ALL CHUNKS VERIFIED")
        print("OVERALL FILE INTEGRITY VERIFIED")

        conn.sendall(
            b"SUCCESS: All chunks and file hash verified"
        )

    except Exception as e:

        print(f"Transfer failed: {e}")

        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        try:
            conn.sendall(
                b"ERROR: Transfer or integrity verification failed"
            )
        except OSError:
            pass

    finally:
        conn.close()
