import time
import csv
import select
import re
from pathlib import Path

from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.log import setLogLevel

from src.network.topology import BackupTopology


CONTROLLER_IP = '127.0.0.1'
CONTROLLER_PORT = 6653

DESTINATION_IP = '10.0.0.3'
PRIMARY_LINK = ('s1', 's2')

PING_INTERVAL = 0.02
TRIALS = 3


def main():

    setLogLevel('warning')

    net = Mininet(
        topo=BackupTopology(),
        controller=None,
        autoSetMacs=True
    )

    net.addController(
        'c0',
        controller=RemoteController,
        ip=CONTROLLER_IP,
        port=CONTROLLER_PORT
    )

    results = []

    try:

        print("\nStarting Mininet...")
        net.start()

        h1 = net.get('h1')

        print("Waiting for SDN controller...")
        time.sleep(5)

        for trial in range(1, TRIALS + 1):

            print(f"\n========== TRIAL {trial} ==========")

            print("Starting continuous ping...")

            ping = h1.popen(
                [
                    'ping',
                    '-D',
                    '-n',
                    '-i', str(PING_INTERVAL),
                    '-c', '500',
                    DESTINATION_IP
                ],
                stdout=-1,
                stderr=-2,
                text=True,
                bufsize=1
            )

            # Allow normal connectivity to establish.
            time.sleep(2)

            print("Disabling primary link S1-S2...")

            failure_time = time.monotonic()

            net.configLinkStatus(
                PRIMARY_LINK[0],
                PRIMARY_LINK[1],
                'down'
            )

            recovered = False
            recovery_time = None
            last_reply_time = None

            # Observe replies for up to 5 seconds.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:

                ready, _, _ = select.select(
                    [ping.stdout],
                    [],
                    [],
                    0.1
                )

                if not ready:
                    continue

                line = ping.stdout.readline()

                if not line:
                    break

                if '64 bytes from' in line:

                    last_reply_time = time.monotonic()

                    if not recovered:

                        recovery_time = (
                            last_reply_time - failure_time
                        )

                        recovered = True

                        print(
                            f"First reply observed after "
                            f"{recovery_time:.4f} seconds"
                        )

            ping.terminate()
            ping.wait()

            if recovered:
                print("Connectivity response observed.")
            else:
                print("Recovery not observed within 5 seconds.")

            # Restore primary link.
            print("Restoring S1-S2...")

            net.configLinkStatus(
                PRIMARY_LINK[0],
                PRIMARY_LINK[1],
                'up'
            )

            time.sleep(3)

            results.append({
                'Trial': trial,
                'Recovery_Time_Seconds': (
                    round(recovery_time, 4)
                    if recovered else 'Timeout'
                ),
                'Recovery_Observed': recovered
            })

        # Save results.
        output_file = Path('results/recovery_results.csv')
        output_file.parent.mkdir(exist_ok=True)

        with output_file.open(
            'w',
            newline=''
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=[
                    'Trial',
                    'Recovery_Time_Seconds',
                    'Recovery_Observed'
                ]
            )

            writer.writeheader()
            writer.writerows(results)

        print("\n========== FINAL RESULTS ==========")

        for result in results:
            print(result)

        print(f"\nResults saved to: {output_file}")

    finally:

        print("\nStopping Mininet...")
        net.stop()


if __name__ == '__main__':
    main()
