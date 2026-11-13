import time
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.log import setLogLevel

from src.network.topology import BackupTopology


CONTROLLER_IP = '127.0.0.1'
CONTROLLER_PORT = 6653

SOURCE_HOST = 'h1'
DESTINATION_HOST = 'h3'
DESTINATION_IP = '10.0.0.3'

PRIMARY_LINK = ('s1', 's2')


def test_connectivity(host):

    result = host.cmd(
        f'ping -c 1 -W 1 {DESTINATION_IP}'
    )

    return '1 received' in result or '1 packets received' in result


def main():

    setLogLevel('info')

    print("\n======================================")
    print("       PATH SWITCH DEMONSTRATION")
    print("======================================")

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

    try:

        print("\n[1] Starting network...")

        net.start()

        h1 = net.get(SOURCE_HOST)
        h3 = net.get(DESTINATION_HOST)

        time.sleep(5)

        print("\n[2] Testing initial connectivity...")

        if not test_connectivity(h1):

            print("ERROR: Initial connectivity failed!")
            return

        print("SUCCESS: H1 can communicate with H3.")

        print("\n[3] Primary path:")
        print("H1 -> S1 -> S2 -> S4 -> H3")

        print("\n[4] Simulating network path change...")

        start_time = time.monotonic()

        net.configLinkStatus(
            PRIMARY_LINK[0],
            PRIMARY_LINK[1],
            'down'
        )

        print("Link S1-S2 disabled.")

        print("\n[5] Waiting for connectivity recovery...")

        recovered = False

        while time.monotonic() - start_time < 30:

            if test_connectivity(h1):

                recovery_time = (
                    time.monotonic() - start_time
                )

                recovered = True
                break

            time.sleep(0.2)

        if recovered:

            print("\nSUCCESS: Connectivity restored!")

            print(
                f"Recovery time: {recovery_time:.3f} seconds"
            )

            print("\n[6] Alternative path:")
            print("H1 -> S1 -> S3 -> S4 -> H3")

        else:

            print("\nERROR: Recovery timed out.")

        print("\n[7] Restoring original network link...")

        net.configLinkStatus(
            PRIMARY_LINK[0],
            PRIMARY_LINK[1],
            'up'
        )

        print("Link S1-S2 restored.")

        time.sleep(3)

        print("\n======================================")
        print("       DEMONSTRATION COMPLETE")
        print("======================================")

    finally:

        print("\nStopping Mininet...")
        net.stop()


if __name__ == '__main__':

    main()
