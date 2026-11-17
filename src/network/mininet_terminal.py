import requests
import shlex
import json
import time

MANAGER = "http://127.0.0.1:5001"

LINKS = {
    ("s1", "s2"),
    ("s2", "s4"),
    ("s1", "s3"),
    ("s3", "s4")
}

HOSTS = ("h1", "h2", "h3", "h4")


# --------------------------------------------------
# GENERAL API REQUEST
# --------------------------------------------------

def post_request(endpoint, payload):
    try:
        response = requests.post(
            f"{MANAGER}{endpoint}",
            json=payload,
            timeout=180
        )

        try:
            result = response.json()
        except ValueError:
            result = response.text

        print(
            json.dumps(result, indent=4)
            if isinstance(result, (dict, list))
            else result
        )

        if not response.ok:
            print(f"HTTP Error: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("ERROR: Mininet manager is not running.")

    except requests.exceptions.Timeout:
        print("ERROR: Request timed out.")

    except requests.exceptions.RequestException as error:
        print(f"ERROR: {error}")


# --------------------------------------------------
# LINK FAILURE AND RESTORE
# --------------------------------------------------

def normalize_link(a, b):
    return tuple(sorted((a.lower(), b.lower())))


def handle_link(parts):

    if len(parts) != 4:
        print("Usage: link s1 s2 down/up")
        return

    switch_a, switch_b, action = parts[1:]

    switch_a = switch_a.lower()
    switch_b = switch_b.lower()
    action = action.lower()

    if switch_a == switch_b:
        print("ERROR: A switch cannot connect to itself.")
        return

    if normalize_link(switch_a, switch_b) not in LINKS:
        print("ERROR: Invalid switch link.")
        print("Valid links: s1-s2, s2-s4, s1-s3, s3-s4")
        return

    payload = {
        "switch_a": switch_a,
        "switch_b": switch_b
    }

    if action == "down":
        post_request("/api/network/failure", payload)

    elif action == "up":
        post_request("/api/network/restore", payload)

    else:
        print("Usage: link s1 s2 down/up")


# --------------------------------------------------
# LIVE BACKUP OUTPUT
# --------------------------------------------------

def handle_backup(parts, mode):

    if len(parts) > 2:
        print(f"Usage: {mode} [filename]")
        return

    if mode == "corrupt":
    	default_filename = "demo_backup.bin"
    else:
    	default_filename = "recovery_test.bin"

    filename = (
    	parts[1] if len(parts) == 2
    	else default_filename
)

    try:

        response = requests.post(
            f"{MANAGER}/api/backup/start",
            json={
                "filename": filename,
                "mode": mode
            },
            timeout=30
        )

        result = response.json()

        if not response.ok:
            print("ERROR:", result)
            return

        print("\n" + "=" * 60)
        print("          DISTRIBUTED BACKUP SYSTEM")
        print("=" * 60)

        print(f"File: {filename}")
        print(f"Mode: {mode.upper()}")
        print("\nStarting transfer...\n")

        printed_lines = 0

        while True:

            status_response = requests.get(
                f"{MANAGER}/api/backup/status",
                timeout=10
            )

            status = status_response.json()

            output = status.get("output", [])

            # Display only newly received output
            for line in output[printed_lines:]:

                clean_line = line.rstrip("\r\n")

                if not clean_line:
                    print()
                    continue

                if "TRANSFER REJECTED" in clean_line:
                    print("\n" + "=" * 60)
                    print("             TRANSFER REJECTED")
                    print("=" * 60)

                elif "TRANSFER SUCCESSFUL" in clean_line:
                    print("\n" + "=" * 60)
                    print("           TRANSFER SUCCESSFUL")
                    print("=" * 60)

                elif "CHECKSUM MISMATCH" in clean_line:
                    print("\n" + "!" * 60)
                    print("             CHECKSUM MISMATCH")
                    print("!" * 60)

                elif "SHA-256" in clean_line:
                    print(f"    {clean_line}")

                elif "chunk" in clean_line.lower():
                    print(f"\n  {clean_line}")

                else:
                    print(f"  {clean_line}")

            printed_lines = len(output)

            if not status.get("running", False):
                break

            time.sleep(0.3)

        print("\n" + "=" * 60)
        print("               TRANSFER FINISHED")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("ERROR: Mininet manager is not running.")

    except requests.exceptions.Timeout:
        print("ERROR: Transfer monitoring timed out.")

    except requests.exceptions.RequestException as error:
        print(f"Transfer monitoring error: {error}")


# --------------------------------------------------
# HELP MENU
# --------------------------------------------------

def show_help():

    print("""
==================================================
             CN-MININET COMMANDS
==================================================

NETWORK TESTING
    pingall
    h1 ping -c 4 h3
    h2 ping -c 4 h4

LINK FAILURE
    link s1 s2 down
    link s1 s2 up

BACKUP TRANSFER
    corrupt
    interrupt
    resume 

CUSTOM FILE TRANSFER
    corrupt filename.bin
    interrupt filename.bin

EXIT
    exit
    quit

==================================================
""")


# --------------------------------------------------
# COMMAND EXECUTION
# --------------------------------------------------

def execute_command(command):

    try:
        parts = shlex.split(command)

    except ValueError as error:
        print(f"Invalid command: {error}")
        return

    if not parts:
        return

    action = parts[0].lower()

    if action in ("exit", "quit"):
        raise SystemExit

    elif action == "help":
        show_help()

    elif action == "link":
        handle_link(parts)

    elif action == "pingall":

        if len(parts) != 1:
            print("Usage: pingall")
        else:
            post_request(
                "/api/network/command",
                {"command": "pingall"}
            )

    elif action in ("corrupt", "interrupt","resume"):
        handle_backup(parts, action)

    elif (
        len(parts) == 5
        and parts[0].lower() in HOSTS
        and parts[1].lower() == "ping"
        and parts[2] == "-c"
        and parts[3].isdigit()
        and 1 <= int(parts[3]) <= 10
        and parts[4].lower() in HOSTS
    ):
        post_request(
            "/api/network/command",
            {"command": command}
        )

    else:
        print("Unknown command. Type 'help' to see available commands.")


# --------------------------------------------------
# MAIN TERMINAL
# --------------------------------------------------

def main():

    print("\n" + "=" * 50)
    print("       DISTRIBUTED BACKUP SYSTEM")
    print("              MININET CLI")
    print("=" * 50)

    print("Type 'help' to see available commands.")

    while True:

        try:
            command = input("\nCN-MININET> ")
            execute_command(command)

        except KeyboardInterrupt:
            print("\nUse 'exit' to close the terminal.")

        except SystemExit:
            print("\nClosing CN-MININET terminal.")
            break


if __name__ == "__main__":
    main()
