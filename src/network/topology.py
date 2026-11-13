from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI


class BackupTopology(Topo):

    def build(self):

        # Clients
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        # Backup servers
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')

        # Open vSwitch switches
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')

        # Connect clients
        self.addLink(h1, s1)
        self.addLink(h2, s1)

        # Connect backup servers
        self.addLink(h3, s2)
        self.addLink(h4, s2)

        # Connect switches
        self.addLink(s1, s2)


if __name__ == '__main__':

    topology = BackupTopology()

    # IMPORTANT: Disable Mininet's default controller
    net = Mininet(
        topo=topology,
        controller=None,
        autoSetMacs=True
    )

    # Connect to our existing OS-Ken controller
    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    net.start()

    print("\nDistributed Backup Network Started!")
    print("Connected to external OS-Ken controller")

    CLI(net)

    net.stop()
