
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI


class BackupTopology(Topo):

    def build(self):

        # Clients
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')

        # Backup servers
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        h4 = self.addHost('h4', ip='10.0.0.4/24')

        # Four OpenFlow 1.3 switches
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', protocols='OpenFlow13')
        s4 = self.addSwitch('s4', protocols='OpenFlow13')

        # Clients connected to S1
        self.addLink(h1, s1)
        self.addLink(h2, s1)

        # Backup servers connected to S4
        self.addLink(h3, s4)
        self.addLink(h4, s4)

        # Two alternative network paths
        self.addLink(s1, s2)
        self.addLink(s2, s4)

        self.addLink(s1, s3)
        self.addLink(s3, s4)


if __name__ == '__main__':

    topology = BackupTopology()

    net = Mininet(
        topo=topology,
        controller=None,
        autoSetMacs=True
    )

    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    net.start()

    print("\nDistributed Backup Network Started!")
    print("Four switches and two alternative paths configured.")
    print("Connected to external OS-Ken controller.")

    CLI(net)

    net.stop()

