import networkx as nx

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet, ether_types
from os_ken.topology import event
from os_ken.topology.api import get_switch, get_link


class PathController(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PathController, self).__init__(*args, **kwargs)

        self.graph = nx.Graph()
        self.datapaths = {}
        self.hosts = {}
        self.link_ports = {}
        self.switch_ports = {}

    # 1. Switch connection
    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):

        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(datapath, 0, match, actions)

        self.logger.info("Switch connected: %s", datapath.id)

    # 2. Install flow rules
    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        idle_timeout=30
    ):

        parser = datapath.ofproto_parser

        instructions = [
            parser.OFPInstructionActions(
                datapath.ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout
        )

        datapath.send_msg(mod)

    # 3. Clear outdated forwarding rules
    def clear_flows(self, datapath):

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch()
        )

        datapath.send_msg(mod)

        # Restore default controller rule
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(
            datapath,
            0,
            parser.OFPMatch(),
            actions
        )

    # 4. Discover network topology
    def discover_topology(self):

        self.graph.clear()
        self.link_ports.clear()
        self.switch_ports.clear()

        switches = get_switch(self, None)
        links = get_link(self, None)

        for switch in switches:

            datapath = switch.dp
            dpid = datapath.id

            self.datapaths[dpid] = datapath
            self.graph.add_node(dpid)

            self.switch_ports[dpid] = {
                port.port_no
                for port in switch.ports
                if port.port_no < datapath.ofproto.OFPP_MAX
            }

        for link in links:

            src = link.src.dpid
            dst = link.dst.dpid

            src_port = link.src.port_no
            dst_port = link.dst.port_no

            self.graph.add_edge(src, dst, weight=1)

            self.link_ports[(src, dst)] = src_port
            self.link_ports[(dst, src)] = dst_port

        self.logger.info(
            "Discovered switches: %s",
            list(self.graph.nodes)
        )

        self.logger.info(
            "Discovered links: %s",
            list(self.graph.edges)
        )

    # 5. Handle topology changes
    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    @set_ev_cls(event.EventSwitchLeave)
    def topology_changed(self, ev):

        self.discover_topology()

        # Clear old forwarding rules
        for datapath in self.datapaths.values():
            self.clear_flows(datapath)

        self.logger.info(
            "Topology updated. Forwarding rules cleared."
        )

    # 6. Calculate shortest path
    def calculate_path(self, source, destination):

        try:

            path = nx.shortest_path(
                self.graph,
                source=source,
                target=destination,
                weight="weight"
            )

            self.logger.info("Selected path: %s", path)

            return path

        except (
            nx.NetworkXNoPath,
            nx.NodeNotFound
        ):

            self.logger.warning(
                "No path between %s and %s",
                source,
                destination
            )

            return None

    # 7. Loop-safe broadcasting
    def broadcast_packet(self, datapath, in_port, data):

        if self.graph.number_of_edges() == 0:
            return

        dpid = datapath.id

        tree = nx.minimum_spanning_tree(self.graph)

        inter_switch_ports = {
            self.link_ports[(dpid, neighbor)]
            for neighbor in self.graph.neighbors(dpid)
            if (dpid, neighbor) in self.link_ports
        }

        host_ports = (
            self.switch_ports.get(dpid, set())
            - inter_switch_ports
        )

        output_ports = set(host_ports)

        for neighbor in tree.neighbors(dpid):

            port = self.link_ports.get((dpid, neighbor))

            if port is not None:
                output_ports.add(port)

        output_ports.discard(in_port)

        actions = [
            datapath.ofproto_parser.OFPActionOutput(port)
            for port in output_ports
        ]

        if not actions:
            return

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=datapath.ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=data
        )

        datapath.send_msg(out)

    # 8. Install forwarding path
    def install_path(
        self,
        path,
        destination_mac,
        destination_port
    ):

        for index, dpid in enumerate(path):

            datapath = self.datapaths.get(dpid)

            if datapath is None:
                return

            if index < len(path) - 1:

                next_switch = path[index + 1]

                out_port = self.link_ports.get(
                    (dpid, next_switch)
                )

            else:

                out_port = destination_port

            if out_port is None:
                return

            parser = datapath.ofproto_parser

            match = parser.OFPMatch(
                eth_dst=destination_mac
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                10,
                match,
                actions
            )

        self.logger.info(
            "Installed path %s for %s",
            path,
            destination_mac
        )

    # 9. Process incoming packets
    @set_ev_cls(
        ofp_event.EventOFPPacketIn,
        MAIN_DISPATCHER
    )
    def packet_in_handler(self, ev):

        msg = ev.msg
        datapath = msg.datapath

        dpid = datapath.id
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)

        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst

        inter_switch_ports = {
            self.link_ports[(dpid, neighbor)]
            for neighbor in self.graph.neighbors(dpid)
            if (dpid, neighbor) in self.link_ports
        } if dpid in self.graph else set()

        # Learn host location
        if in_port not in inter_switch_ports:

            self.hosts[src] = (dpid, in_port)

            self.logger.info(
                "Learned host %s at switch %s port %s",
                src,
                dpid,
                in_port
            )

        # Broadcast or unknown destination
        if (
            dst == "ff:ff:ff:ff:ff:ff"
            or dst not in self.hosts
        ):

            self.broadcast_packet(
                datapath,
                in_port,
                msg.data
            )

            return

        destination_dpid, destination_port = self.hosts[dst]

        path = self.calculate_path(
            dpid,
            destination_dpid
        )

        if path is None:
            return

        self.install_path(
            path,
            dst,
            destination_port
        )

        if dpid == destination_dpid:

            out_port = destination_port

        else:

            out_port = self.link_ports.get(
                (dpid, path[1])
            )

        if out_port is None:
            return

        actions = [
            datapath.ofproto_parser.OFPActionOutput(out_port)
        ]

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )

        datapath.send_msg(out)
