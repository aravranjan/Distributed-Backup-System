from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller
from mininet.cli import CLI


class BackupTopology(Topo):

    def build(self):

        # Create two clients
        client1 = self.addHost('h1')
        client2 = self.addHost('h2')

        # Create two backup servers
        server1 = self.addHost('h3')
        server2 = self.addHost('h4')

        # Create two Open vSwitch switches
        switch1 = self.addSwitch('s1')
        switch2 = self.addSwitch('s2')

        # Connect clients to switch 1
        self.addLink(client1, switch1)
        self.addLink(client2, switch1)

        # Connect servers to switch 2
        self.addLink(server1, switch2)
        self.addLink(server2, switch2)

        # Connect both switches
        self.addLink(switch1, switch2)


if __name__ == '__main__':

    topology = BackupTopology()

    net = Mininet(
        topo=topology,
        controller=Controller
    )

    net.start()

    print("\nDistributed Backup Network Started!")
    print("2 Clients, 2 Backup Servers, 2 Switches")

    CLI(net)

    net.stop()
