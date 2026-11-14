import socket
import os
import struct
import hashlib
import json
import time

HOST = '0.0.0.0'
PORT = 5001

CHUNK_SIZE = 1024 * 1024
SAVE_DIR = os.environ.get(
    'BACKUP_SAVE_DIR',
    'backups'
)

# Configurable testing delay (default: 0 seconds)
CHUNK_DELAY_SECONDS = float(
    os.getenv('CHUNK_DELAY_SECONDS', '0')
)

os.makedirs(SAVE_DIR, exist_ok=True)


def receive_exact(conn, size):
    data = b''

    while len(data) < size:
        chunk = conn.recv(size - len(data))

        if not chunk:
            raise ConnectionError("Connection interrupted")

        data += chunk

    return data


def send_message(conn, message):
    data = message.encode()
    conn.sendall(struct.pack('!I', len(data)) + data)


def save_manifest(path, manifest):
    temporary_path = path + '.tmp'

    with open(temporary_path, 'w') as file:
        json.dump(manifest, file)

    os.replace(temporary_path, path)


def handle_client(conn, addr):

    print(f"\nConnected to client: {addr}")

    try:
        # 1. Receive file metadata
        header = receive_exact(conn, 18)

        filename_length, file_size, chunk_size, total_chunks = (
            struct.unpack('!HQII', header)
        )

        if filename_length == 0 or filename_length > 255:
            raise ValueError("Invalid filename length")

        if chunk_size != CHUNK_SIZE:
            raise ValueError("Invalid chunk size")

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

        original_hash = receive_exact(conn, 32).hex()

        # 2. Identify this particular backup
        filepath = os.path.join(
            SAVE_DIR, filename + '.part'
        )

        manifest_path = os.path.join(
            SAVE_DIR, filename + '.json'
        )

        manifest = None

        # 3. Check whether a previous transfer exists
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r') as file:
                    existing = json.load(file)

                if (
                    existing['file_size'] == file_size
                    and existing['chunk_size'] == chunk_size
                    and existing['total_chunks'] == total_chunks
                    and existing['original_hash'] == original_hash
                    and os.path.exists(filepath)
                ):
                    manifest = existing

                    print("Previous interrupted transfer found.")

            except (OSError, ValueError, KeyError, TypeError):
                manifest = None

        # 4. Create a fresh partial backup if necessary
        if manifest is None:

            manifest = {
                'filename': filename,
                'file_size': file_size,
                'chunk_size': chunk_size,
                'total_chunks': total_chunks,
                'original_hash': original_hash,
                'completed_chunks': {}
            }

            with open(filepath, 'wb') as file:
                file.truncate(file_size)

            save_manifest(manifest_path, manifest)

            print("Starting a new backup.")

        # 5. Recheck previously saved chunks
        valid_chunks = {}

        with open(filepath, 'rb') as file:

            for sequence, saved_hash in (
                manifest['completed_chunks'].items()
            ):
                sequence = int(sequence)

                if not 0 <= sequence < total_chunks:
                    continue

                expected_length = min(
                    chunk_size,
                    file_size - sequence * chunk_size
                )

                file.seek(sequence * chunk_size)
                data = file.read(expected_length)

                if (
                    len(data) == expected_length
                    and hashlib.sha256(data).hexdigest() == saved_hash
                ):
                    valid_chunks[str(sequence)] = saved_hash

        manifest['completed_chunks'] = valid_chunks
        save_manifest(manifest_path, manifest)

        # 6. Tell client which chunks are missing
        missing_chunks = [
            i for i in range(total_chunks)
            if str(i) not in valid_chunks
        ]

        conn.sendall(struct.pack('!I', len(missing_chunks)))

        for sequence in missing_chunks:
            conn.sendall(struct.pack('!I', sequence))

        print(f"Already verified: {len(valid_chunks)} chunks")
        print(f"Remaining chunks: {len(missing_chunks)}")

        # 7. Receive only missing chunks
        with open(filepath, 'r+b') as file:

            for expected_sequence in missing_chunks:

                chunk_header = receive_exact(conn, 8)

                sequence, chunk_length = struct.unpack(
                    '!II', chunk_header
                )

                expected_length = min(
                    chunk_size,
                    file_size - sequence * chunk_size
                )

                if sequence != expected_sequence:
                    raise ValueError("Invalid chunk sequence")

                if chunk_length != expected_length:
                    raise ValueError("Invalid chunk length")

                chunk_hash = receive_exact(conn, 32)
                chunk_data = receive_exact(conn, chunk_length)

                calculated_hash = hashlib.sha256(
                    chunk_data
                ).digest()

                if calculated_hash != chunk_hash:
                    raise ValueError(
                        f"Chunk {sequence} checksum failed"
                    )

                # Save chunk at its correct position
                file.seek(sequence * chunk_size)
                file.write(chunk_data)
                file.flush()
                os.fsync(file.fileno())

                # Record verified chunk
                manifest['completed_chunks'][str(sequence)] = (
                    calculated_hash.hex()
                )

                save_manifest(manifest_path, manifest)

                print(
                    f"Verified and saved chunk "
                    f"{sequence + 1}/{total_chunks}"
                )

                # Optional delay for failure simulation
                if CHUNK_DELAY_SECONDS > 0:
                    time.sleep(CHUNK_DELAY_SECONDS)

        # 8. Verify the complete reconstructed file
        overall_hash = hashlib.sha256()

        with open(filepath, 'rb') as file:
            while True:
                data = file.read(4096)

                if not data:
                    break

                overall_hash.update(data)

        if overall_hash.hexdigest() != original_hash:
            raise ValueError("Overall SHA-256 mismatch")

        # 9. Finalize backup
        final_path = os.path.join(SAVE_DIR, filename)

        os.replace(filepath, final_path)
        os.remove(manifest_path)

        print(f"File received successfully: {filename}")
        print("ALL CHUNKS VERIFIED")
        print("OVERALL SHA-256 VERIFIED")

        send_message(
            conn,
            "SUCCESS: File transferred and verified"
        )

    except Exception as e:

        print(f"Transfer interrupted or failed: {e}")

        # Keep the partial file and manifest for recovery.

        try:
            send_message(
                conn,
                f"ERROR: {e}"
            )
        except OSError:
            pass

    finally:
        conn.close()


# Main server
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
    handle_client(conn, addr)
