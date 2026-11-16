
import requests
import shlex
import json

MANAGER = "http://127.0.0.1:5001"

LINKS = {
    ("s1", "s2"),
    ("s2", "s4"),
    ("s1", "s3"),
    ("s3", "s4")
}


def post_request(endpoint, payload):
    """Send a POST request to the existing Mininet manager."""

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

        print(json.dumps(result, indent=4)
              if isinstance(result, (dict, list))
              else result)

        if not response.ok:
            print(f"HTTP Error: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("ERROR: Mininet manager is not running.")
        print("Start it using:")
        print("sudo python3 src/network/mininet_manager.py")

    except requests.exceptions.Timeout:
        print("ERROR: Request timed out.")

    except requests.exceptions.RequestException as error:
        print(f"ERROR: {error}")


def normalize_link(a, b):
    return tuple(sorted((a.lower(), b.lower())))


def handle_link(parts):
    """Handle link failure and restoration."""

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


def execute_command(command):
    """Process a command entered by the user."""

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

    elif action in ("pingall", "corrupt", "interrupt"):
        post_request(
            "/api/network/command",
            {"command": command}
        )

    elif len(parts) >= 5 and parts[1] == "ping":
        post_request(
            "/api/network/command",
            {"command": command}
        )

    else:
        print("Unknown command. Type 'help' to see available commands.")


def show_help():

    print("""
====================================================
        DISTRIBUTED BACKUP - MININET TERMINAL
====================================================

NETWORK CONNECTIVITY
--------------------
pingall
h1 ping -c 4 h3
h1 ping -c 4 h4
h2 ping -c 4 h3
h2 ping -c 4 h4

LINK FAILURE SIMULATION
-----------------------
link s1 s2 down
link s1 s2 up

link s1 s3 down
link s1 s3 up

link s2 s4 down
link s2 s4 up

link s3 s4 down
link s3 s4 up

BACKUP FAILURE TESTING
----------------------
corrupt
interrupt

OTHER COMMANDS
--------------
help
exit

====================================================
""")


def main():

    print("\n==============================================")
    print("       DISTRIBUTED BACKUP MININET CLI")
    print("==============================================")
    print("Connected manager:", MANAGER)
    print("Type 'help' for available commands.")
    print("Type 'exit' to close the terminal.\n")

    while True:

        try:
            command = input("CN-MININET> ").strip()
            execute_command(command)

        except KeyboardInterrupt:
            print("\nUse 'exit' to close the terminal.")

        except EOFError:
            break

        except SystemExit:
            print("Closing Mininet terminal.")
            break


if __name__ == "__main__":
    main()

