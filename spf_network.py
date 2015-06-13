import networkx as nx
import matplotlib.pyplot as plt
try:
    from pox.core import core
    from pox.lib.packet.arp import arp
    from pox.lib.packet.ipv4 import ipv4
    from pox.lib.addresses import IPAddr, EthAddr
    from pox.proto.arp_helper import *  
    from pox.openflow.discovery import Discovery
    import pox.openflow.libopenflow_01 as of
    from pox.lib.util import dpid_to_str
    log = core.getLogger()
except Exception:
    pass
else:
    import logging
    log = logging.getLogger(__name__)

colormap = { 'host': 'red', 'switch': 'green'}
G = nx.Graph()
switches = {}

class Switch(object):
    
    def __init__(self, dpid, connection, n):
        self.dpid = dpid
        self.connection = connection
        self.n = n
        self.flow_table = {}  # destination : outport
        self.neighbourtable = {} # host mac: port
        self.uplinkports = {} # port : dpid
    
    def add_host(self, mac, port):
        self.n.add_host(str(packet.src)) # only unique is added
        # check if we need create a link for this host
        if str(packet_in.in_port) not in self.uplinkports.keys():
            N.add_link(str(self.dpid), str(packet.src))
            N.path_recalc()  # update all swicthes

    def add_flow(self, dst, port):
        log.debug("{0}:add_flow: {1} to port: {2}".format(dpid_to_str(self.dpid), dst,port,self.connection))
        msg = of.ofp_flow_mod(command=of.OFPFC_ADD)
        msg.match.dl_dst = dst
        msg.actions.append(of.ofp_action_output(port = port))
        self.connection.send(msg)
        
    def rm_flow(self, dst, port):
        log.debug("{0}:rm_flow: {1} to port: {2}".format(dpid_to_str(self.dpid), dst,port,self.connection))
        msg = of.ofp_flow_mod(command=of.OFPFC_DELETE)
        msg.match.dl_dst = dst
        msg.actions.append(of.ofp_action_output(port = port))
        self.connection.send(msg)

    def clear_flowtable(self):
        msg = of.ofp_flow_mod(command=of.OFPFC_DELETE)
        self.connection.send(msg)
        log.debug("%s: Clearing all flows!" % (dpid_to_str(self.dpid)))


class SwitchHandler(object):
    """
    A PoxSPF object is created for each switch that connects.
    A Connection object for that switch is passed to the __init__ function.
    """
    def __init__ (self, sw):
        self.sw = sw
        # This binds our PacketIn event listener
        connection.addListeners(self)
        #connection.addListeners("LinkEvent", start_switch
        core.openflow_discovery.addListenerByName("LinkEvent", self._handle_LinkEvent)

    def _handle_PacketIn (self, event):
        """
        Handles packet in messages from the switch.
        """
        packet = event.parsed # This is the parsed packet data.
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp # The actual ofp_packet_in message.

        self.sw.add_host(packet.src) # only unique is added
        
        #self.sw.id_to_port[str(packet.src)] = packet_in.in_port
        # create a flow for any packet matching this src to output
        # to this port
        #self._add_flow(packet.src, packet_in.in_port)
        # update the other switches so they know about this target
        #for sw in switches.values():
        #    log.debug("update sw:{0}, {1}:{2}".format(sw.dpid, packet.src, self.dpid))
        #    sw.update_mac_dst(packet.src, self.dpid)

        #self.act_like_l3_switch(event)

        # now let's see what we can do with this packet
        if packet.dst not in self.mac_to_port:
            # if we don't know the destination flood the packet, 
            # this way we learn mac addresses as well
            # better would be in case of IP to do an ARP request for the ipaddress
            # however this works just as well, just less secure
            log.debug("HELLUP we don't know dst: {0}".format(packet.dst))

            #for mac in self.mac_to_port.keys():
            if str(packet.dst) in G.nodes():
                path = nx.dijkstra_path(G, str(self.dpid), str(packet.dst))
                if len(path) == 2:
                    self._add_flow(packet.dst, self.mac_to_port[packet.dst])
                else:
                    self._add_flow(packet.dst, self.uplinks[path[1]])
            #self.resend_packet(packet_in, of.OFPP_ALL)
            return
        else:
            self._add_flow(packet.dst, self.mac_to_port[packet.dst])


class SPFNetwork(object):

    def __init__(self, *args, **kwargs):
        self.add_switch("1")
        self.add_switch("2")
        self.add_switch("3")
        self.add_link("1","2")
        self.add_link("2", "3")
        self.add_link("3", "1")
        self.add_host("a")
        self.add_link("1","a")
        self.add_host("b")
        self.add_link("2","b")
        self.add_host("c")
        self.add_link("3","c")
        self.path_recalc()
        plt.ion()
        #self.run()
   
    def add_switch(self, id_):
        G.add_node(id_, tp="switch")
        self.redraw()

    def add_host(self, id_):
        G.add_node(id_, tp="host")
        self.redraw()

    def add_link(self, _from, _to, weight=1):
        G.add_edge(_from, _to, weight=weight)
        self.redraw()

    def rm_switch(self, id_):
        G.remove_node(id_)
        self.redraw()

    def rm_host(self, id_):
        G.remove_node(id_)
        self.redraw()

    def rm_link(self, _from, _to, weight=1):
        G.remove_edge(_from, _to)
        self.redraw()
    
    def path_recalc(self):
        for switch in G.nodes(data=True):
            if switch[1]['tp'] == "switch":
                print("NEXT HOPS FOR SWITCH: {0}".format(switch[0]))
                for host in G.nodes():
                    try:
                        path = nx.shortest_path(G, switch[0], host)
                    except nx.exception.NetworkXNoPath:
                        pass
                    else:
                        print(path)
                        if len(path) > 1:
                            print("FROM {0} TO {1}: {2}".format(switch[0], host, path[1]))
    
    def redraw(self):
        plt.clf()
        colors = [colormap.get(node[1]['tp']) for node in G.nodes(data=True)]
        nx.draw(G, node_color=colors)
        plt.draw()

    def run(self):
        while True:
            self.redraw()
            try:
                msg = input()
                try:
                    h,s = msg.split(',')
                except:
                    break
                self.add_host(h)
                self.add_switch(s)
                self.add_link(h,s)
                self.path_recalc()
                print(msg)
            except (KeyboardInterrupt, SystemExit):
                break

def launch ():
    """
    Starts the component
    """
    def start_switch (event):
        log.debug("Controlling {0}:{1}".format(event.connection,event.dpid))
        sw = switches.get(event.dpid)
        if sw is None:
            # New switch
            sw = Switch(event.dpid, event.connection, N)
            N.add_switch(event.dpid)
            switches[event.dpid] = sw
        else:
            sw.connect(event.connection)

        PoxSPF(event.connection, sw)
    N = SPFNetwork()
    core.openflow.addListenerByName("ConnectionUp", start_switch)
    #core.openflow.addListenerByName("LinkEvent", start_switch)


#`if __name__ == "__main__":
    #N = SPFNetwork()
