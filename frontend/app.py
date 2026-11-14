from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    stream_with_context
)

from pathlib import Path
from urllib.parse import quote

import csv
import requests


app = Flask(__name__)

# ======================================================
# CONFIGURATION
# ======================================================

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "test_files"
RESULTS_DIR = BASE_DIR / "results"

CONTROLLER_API = "http://127.0.0.1:8080"
MANAGER_API = "http://127.0.0.1:5001"

UPLOAD_DIR.mkdir(exist_ok=True)


# ======================================================
# HELPER FUNCTIONS
# ======================================================

def manager_request(method, endpoint, **kwargs):

    try:

        response = requests.request(
            method,
            f"{MANAGER_API}{endpoint}",
            timeout=60,
            **kwargs
        )

        try:
            data = response.json()
        except ValueError:
            data = {"error": response.text}

        return jsonify(data), response.status_code

    except requests.RequestException as error:

        return jsonify({
            "error": "Mininet manager unavailable",
            "details": str(error)
        }), 503


def valid_server(name):
    return name in ("h3", "h4")


# ======================================================
# DASHBOARD
# ======================================================

@app.route("/")
def dashboard():

    return render_template("index.html")


# ======================================================
# SDN CONTROLLER API
# ======================================================

@app.route("/api/topology")
def get_topology():

    try:

        response = requests.get(
            f"{CONTROLLER_API}/api/topology",
            timeout=3
        )

        response.raise_for_status()

        return jsonify(response.json())

    except requests.RequestException as error:

        return jsonify({
            "status": "unavailable",
            "error": str(error)
        }), 503


# ======================================================
# METRICS API
# ======================================================

@app.route("/api/metrics")
def get_metrics():

    metrics = {
        "throughput": [],
        "recovery": []
    }

    throughput_file = RESULTS_DIR / "throughput_results.csv"
    recovery_file = RESULTS_DIR / "recovery_results.csv"

    if throughput_file.exists():

        with open(throughput_file, newline="") as file:
            metrics["throughput"] = list(
                csv.DictReader(file)
            )

    if recovery_file.exists():

        with open(recovery_file, newline="") as file:
            metrics["recovery"] = list(
                csv.DictReader(file)
            )

    return jsonify(metrics)


# ======================================================
# FILE UPLOAD API
# ======================================================

@app.route("/api/upload", methods=["POST"])
def upload_file():

    if "file" not in request.files:
        return jsonify({"error": "No file selected"}), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = Path(file.filename).name

    if filename in ("", ".", ".."):
        return jsonify({"error": "Invalid filename"}), 400

    destination = UPLOAD_DIR / filename

    file.save(destination)

    return jsonify({
        "message": "File uploaded successfully",
        "filename": filename,
        "size": destination.stat().st_size
    })


# ======================================================
# MININET NETWORK MANAGEMENT
# ======================================================

@app.route("/api/network/start", methods=["POST"])
def start_network():

    return manager_request(
        "POST",
        "/api/network/start"
    )


@app.route("/api/network/stop", methods=["POST"])
def stop_network():

    return manager_request(
        "POST",
        "/api/network/stop"
    )


@app.route("/api/network/status")
def network_status():

    return manager_request(
        "GET",
        "/api/network/status"
    )


# ======================================================
# BACKUP SERVER MANAGEMENT
# ======================================================

# Start both servers
@app.route("/api/servers/start", methods=["POST"])
def start_servers():

    return manager_request(
        "POST",
        "/api/servers/start"
    )


# Get status of both servers
@app.route("/api/servers/status")
def server_status():

    return manager_request(
        "GET",
        "/api/servers/status"
    )


# Start an individual server
@app.route(
    "/api/servers/<server>/start",
    methods=["POST"]
)
def start_individual_server(server):

    if not valid_server(server):
        return jsonify({"error": "Invalid server"}), 400

    return manager_request(
        "POST",
        f"/api/servers/{server}/start"
    )


# Stop an individual server
@app.route(
    "/api/servers/<server>/stop",
    methods=["POST"]
)
def stop_individual_server(server):

    if not valid_server(server):
        return jsonify({"error": "Invalid server"}), 400

    return manager_request(
        "POST",
        f"/api/servers/{server}/stop"
    )


# List files stored on an individual server
@app.route(
    "/api/servers/<server>/files",
    methods=["GET"]
)
def server_files(server):

    if not valid_server(server):
        return jsonify({"error": "Invalid server"}), 400

    return manager_request(
        "GET",
        f"/api/servers/{server}/files"
    )


# Download a file from an individual server
@app.route(
    "/api/servers/<server>/download/<filename>",
    methods=["GET"]
)
def download_server_file(server, filename):

    if not valid_server(server):
        return jsonify({"error": "Invalid server"}), 400

    if Path(filename).name != filename:
        return jsonify({"error": "Invalid filename"}), 400

    try:

        upstream = requests.get(
            f"{MANAGER_API}/api/servers/{server}/download/{quote(filename, safe='')}",
            stream=True,
            timeout=(5, 60)
        )

        if upstream.status_code != 200:

            try:
                data = upstream.json()
            except ValueError:
                data = {"error": upstream.text}

            upstream.close()

            return jsonify(data), upstream.status_code

        headers = {}

        if "Content-Disposition" in upstream.headers:
            headers["Content-Disposition"] = (
                upstream.headers["Content-Disposition"]
            )

        headers["Content-Type"] = upstream.headers.get(
            "Content-Type",
            "application/octet-stream"
        )

        def generate():

            try:
                for chunk in upstream.iter_content(
                    chunk_size=64 * 1024
                ):
                    if chunk:
                        yield chunk

            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            headers=headers,
            direct_passthrough=True
        )

    except requests.RequestException as error:

        return jsonify({
            "error": "Download failed",
            "details": str(error)
        }), 503


# ======================================================
# NETWORK FAILURE SIMULATION
# ======================================================

@app.route("/api/network/failure", methods=["POST"])
def simulate_failure():

    data = request.get_json(silent=True) or {}

    return manager_request(
        "POST",
        "/api/network/failure",
        json=data
    )


@app.route("/api/network/restore", methods=["POST"])
def restore_network():

    data = request.get_json(silent=True) or {}

    return manager_request(
        "POST",
        "/api/network/restore",
        json=data
    )


# ======================================================
# BACKUP TRANSFER
# ======================================================

@app.route("/api/backup/start", methods=["POST"])
def start_backup():

    data = request.get_json(silent=True) or {}

    return manager_request(
        "POST",
        "/api/backup/start",
        json=data
    )


@app.route("/api/backup/status")
def backup_status():

    return manager_request(
        "GET",
        "/api/backup/status"
    )


# ======================================================
# START FLASK
# ======================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
