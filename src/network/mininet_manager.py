
from flask import Flask, jsonify, request, send_file
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.log import setLogLevel
from topology import BackupTopology

from pathlib import Path
import threading
import subprocess
import time
import os
import re

app = Flask(__name__)

# ======================================================
# CONFIGURATION
# ======================================================

BASE_DIR = Path("/home/arav/CN-Lab-Project")

SERVER_SCRIPT = BASE_DIR / "src/server/backup_server.py"
CLIENT_SCRIPT = BASE_DIR / "src/client/backup_client.py"

STORAGE_DIRS = {
    "h3": Path("/var/lib/distributed-backup/h3/backups"),
    "h4": Path("/var/lib/distributed-backup/h4/backups")
}

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

net = None

network_lock = threading.RLock()
server_lock = threading.RLock()
transfer_lock = threading.Lock()

server_processes = {
    "h3": None,
    "h4": None
}

transfer_process = None
transfer_output = []


# ======================================================
# MININET HELPERS
# ======================================================

def get_host(name):

    if net is None:
        raise RuntimeError("Network is not running")

    return net.get(name)


def start_network():

    global net

    with network_lock:

        if net is not None:
            return False

        topology = BackupTopology()

        net = Mininet(
            topo=topology,
            controller=None,
            autoSetMacs=True
        )

        net.addController(
            "c0",
            controller=RemoteController,
            ip="127.0.0.1",
            port=6653
        )

        net.start()

        return True


def stop_network():

    global net

    with network_lock:

        if net is None:
            return

        stop_server("h3")
        stop_server("h4")

        net.stop()
        net = None


# ======================================================
# SERVER MANAGEMENT
# ======================================================

def valid_server(name):
    return name in ("h3", "h4")


def server_is_online(name):

    if not valid_server(name) or net is None:
        return False

    host = get_host(name)

    result = host.cmd(
        "ss -ltn | grep -q ':5001'; echo $?"
    )

    return result.strip().endswith("0")


def start_server(name):

    if not valid_server(name):
        raise ValueError("Invalid backup server")

    with server_lock:

        host = get_host(name)

        if server_is_online(name):
            return False

        storage = STORAGE_DIRS[name]
        storage.mkdir(parents=True, exist_ok=True)

        log_path = LOG_DIR / f"{name}_backup.log"

        environment = os.environ.copy()
        environment["BACKUP_SAVE_DIR"] = str(storage)

        with open(log_path, "a") as log_file:

            process = host.popen(
                ["python3", str(SERVER_SCRIPT)],
                cwd=str(BASE_DIR),
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )

        server_processes[name] = process

        for _ in range(30):

            time.sleep(0.1)

            if server_is_online(name):
                return True

            if process.poll() is not None:
                break

        raise RuntimeError(
            f"{name.upper()} failed to start. "
            f"Check {log_path}"
        )


def stop_server(name):

    if not valid_server(name):
        raise ValueError("Invalid backup server")

    with server_lock:

        host = get_host(name)
        process = server_processes.get(name)

        if process is not None and process.poll() is None:

            process.terminate()

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                process.kill()
                process.wait(timeout=3)

            server_processes[name] = None
            return True

        # Recover a server process started by an older manager.
        output = host.cmd(
            "ss -ltnp 'sport = :5001'"
        )

        match = re.search(r"pid=(\d+)", output)

        if match:

            pid = int(match.group(1))

            command = host.cmd(
                f"tr '\\0' ' ' < /proc/{pid}/cmdline"
            )

            if "backup_server.py" in command:

                host.cmd(f"kill {pid}")
                time.sleep(0.5)

                server_processes[name] = None
                return True

        server_processes[name] = None
        return False


def get_server_status():

    return {
        "h3": server_is_online("h3"),
        "h4": server_is_online("h4")
    }


# ======================================================
# NETWORK START / STOP
# ======================================================

@app.route("/api/network/start", methods=["POST"])
def api_start_network():

    try:

        started = start_network()

        return jsonify({
            "status": "running",
            "message": (
                "Network started"
                if started
                else "Network already running"
            )
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


@app.route("/api/network/stop", methods=["POST"])
def api_stop_network():

    try:

        stop_network()

        return jsonify({
            "status": "stopped",
            "message": "Network stopped"
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


@app.route("/api/network/status")
def api_network_status():

    return jsonify({
        "running": net is not None
    })


# ======================================================
# INDIVIDUAL SERVER START / STOP
# ======================================================

@app.route("/api/servers/<name>/start", methods=["POST"])
def api_start_server(name):

    try:

        if not valid_server(name):
            return jsonify({"error": "Invalid server"}), 404

        started = start_server(name)

        return jsonify({
            "server": name,
            "online": True,
            "message": (
                f"{name.upper()} started"
                if started
                else f"{name.upper()} is already running"
            )
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


@app.route("/api/servers/<name>/stop", methods=["POST"])
def api_stop_server(name):

    try:

        if not valid_server(name):
            return jsonify({"error": "Invalid server"}), 404

        stopped = stop_server(name)

        return jsonify({
            "server": name,
            "online": server_is_online(name),
            "message": (
                f"{name.upper()} stopped"
                if stopped
                else f"{name.upper()} was not running"
            )
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


# ======================================================
# START BOTH SERVERS
# ======================================================

@app.route("/api/servers/start", methods=["POST"])
def api_start_servers():

    try:

        start_server("h3")
        start_server("h4")

        return jsonify({
            "message": "Backup servers started",
            **get_server_status()
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


# ======================================================
# SERVER STATUS
# ======================================================

@app.route("/api/servers/status")
def api_server_status():

    try:

        return jsonify(get_server_status())

    except Exception as error:

        return jsonify({"error": str(error)}), 500


# ======================================================
# LIST FILES STORED ON BACKUP SERVER
# ======================================================

@app.route("/api/servers/<name>/files")
def api_server_files(name):

    if not valid_server(name):
        return jsonify({"error": "Invalid server"}), 404

    if not server_is_online(name):
        return jsonify({
            "error": "Backup server is offline"
        }), 409

    storage = STORAGE_DIRS[name]

    files = []

    if storage.exists():

        for path in storage.iterdir():

            if not path.is_file():
                continue

            if path.name.endswith((".tmp", ".json")):
                continue

            stat = path.stat()

            files.append({
                "filename": path.name,
                "size": stat.st_size,
                "size_mib": round(
                    stat.st_size / (1024 * 1024), 2
                ),
                "modified": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(stat.st_mtime)
                )
            })

    return jsonify({
        "server": name,
        "files": files,
        "count": len(files)
    })


# ======================================================
# DOWNLOAD BACKUP FILE
# ======================================================

@app.route(
    "/api/servers/<name>/download/<filename>"
)
def api_download_file(name, filename):

    if not valid_server(name):
        return jsonify({"error": "Invalid server"}), 404

    if not server_is_online(name):
        return jsonify({
            "error": "Backup server is offline"
        }), 409

    if (
        filename in ("", ".", "..")
        or Path(filename).name != filename
    ):
        return jsonify({"error": "Invalid filename"}), 400

    storage = STORAGE_DIRS[name]
    file_path = storage / filename

    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename
    )


# ======================================================
# NETWORK FAILURE SIMULATION
# ======================================================

ALLOWED_LINKS = {
    frozenset(("s1", "s2")),
    frozenset(("s2", "s4")),
    frozenset(("s1", "s3")),
    frozenset(("s3", "s4"))
}


@app.route("/api/network/failure", methods=["POST"])
def api_link_failure():

    try:

        if net is None:
            return jsonify({
                "error": "Network is not running"
            }), 400

        data = request.get_json(silent=True) or {}

        switch_a = data.get("switch_a", "s1")
        switch_b = data.get("switch_b", "s2")

        if frozenset((switch_a, switch_b)) not in ALLOWED_LINKS:
            return jsonify({
                "error": "Invalid switch link"
            }), 400

        net.configLinkStatus(
            switch_a,
            switch_b,
            "down"
        )

        return jsonify({
            "message": f"Link {switch_a}-{switch_b} disabled"
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


@app.route("/api/network/restore", methods=["POST"])
def api_restore_link():

    try:

        if net is None:
            return jsonify({
                "error": "Network is not running"
            }), 400

        data = request.get_json(silent=True) or {}

        switch_a = data.get("switch_a", "s1")
        switch_b = data.get("switch_b", "s2")

        if frozenset((switch_a, switch_b)) not in ALLOWED_LINKS:
            return jsonify({
                "error": "Invalid switch link"
            }), 400

        net.configLinkStatus(
            switch_a,
            switch_b,
            "up"
        )

        return jsonify({
            "message": f"Link {switch_a}-{switch_b} restored"
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


# ======================================================
# BACKUP TRANSFER
# ======================================================

@app.route("/api/backup/start", methods=["POST"])
def api_start_backup():

    global transfer_process, transfer_output

    try:

        if net is None:
            return jsonify({
                "error": "Network is not running"
            }), 400

        data = request.get_json(silent=True) or {}

        filename = data.get("filename")
        mode = data.get("mode", "normal")

        if (
            not filename
            or Path(filename).name != filename
        ):
            return jsonify({
                "error": "Invalid filename"
            }), 400

        file_path = BASE_DIR / "test_files" / filename

        if not file_path.is_file():
            return jsonify({
                "error": "Uploaded file not found"
            }), 404

        options = {
            "normal": [],
            "corrupt": ["--corrupt"],
            "interrupt": ["--interrupt"]
        }

        if mode not in options:
            return jsonify({
                "error": "Invalid transfer mode"
            }), 400

        command = [
            "python3",
            str(CLIENT_SCRIPT),
            "--auto",
            str(file_path),
            *options[mode]
        ]

        h1 = get_host("h1")

        with transfer_lock:

            if (
                transfer_process is not None
                and transfer_process.poll() is None
            ):
                return jsonify({
                    "error": "A transfer is already running"
                }), 409

            transfer_output = []

            transfer_process = h1.popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            threading.Thread(
                target=read_transfer_output,
                args=(transfer_process,),
                daemon=True
            ).start()

        return jsonify({
            "message": "Backup started",
            "filename": filename,
            "mode": mode
        })

    except Exception as error:

        return jsonify({"error": str(error)}), 500


def read_transfer_output(process):

    global transfer_output

    for line in process.stdout:

        with transfer_lock:
            transfer_output.append(line.rstrip())


@app.route("/api/backup/status")
def api_backup_status():

    with transfer_lock:

        output = list(transfer_output)

        running = (
            transfer_process is not None
            and transfer_process.poll() is None
        )

        return jsonify({
            "running": running,
            "output": output,
            "return_code": (
                transfer_process.poll()
                if transfer_process is not None
                else None
            )
        })


# ======================================================
# START MANAGEMENT SERVICE
# ======================================================

if __name__ == "__main__":

    setLogLevel("warning")

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        threaded=True
    )

