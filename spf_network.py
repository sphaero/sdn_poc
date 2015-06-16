import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
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

from pyre_loop import PyreEvent
import pickle

colormap = { 'host': 'red', 'switch': 'green', 'remoteswitch': 'blue'}
G = nx.Graph()
switches = {}

#
# Start two controllers like this:
# PYTHONPATH="../../:/home/people/arnaud/src/pyre/" ./pox.py log.level --DEBUG sdn_poc.pyre_loop sdn_poc.spf_network --id=0 openflow.discovery
# PYTHONPATH="../../:/home/people/arnaud/src/pyre/" ./pox.py openflow.of_01 --port=6634 log.level --DEBUG sdn_poc.pyre_loop sdn_poc.spf_network --id=1 openflow.discovery
#
# distopo.py is an example script to setup mininet for this
#

class Switch(object):
    
    def __init__(self, dpid, connection, n):
        self.dpid = dpid
        self.connection = connection
        self.n = n
        self.flow_table = {}        # destination : outport
        self.neighbourtable = {}    # host mac: port
        self.uplinkports = {}       # port : dpid
    
    def add_host(self, mac, port):
        log.debug("{1}:add host {0}".format(mac,dpid_to_str(self.dpid)))
        self.n.add_host(mac)        # only unique is added
        # check if we need create a link for this host
        if port not in self.uplinkports.keys():
            self.n.add_link(self.dpid, mac, port)
            if mac not in self.neighbourtable.keys():   # perhaps also check values?
                self.neighbourtable[mac] = port         # we don't know this host yet 
                #self.n.path_recalc()                    # update all swicthes
    
    def add_uplink(self, port, sw_dpid, sw_port=None):
        self.uplinkports[port] = sw_dpid
        self.n.add_link(self.dpid, sw_dpid, "{0}:{1}".format(port, sw_port))

    def rm_uplink(self, port, sw_dpid):
        try:
            self.uplinkports.pop(port)
        except KeyError:
            pass
        self.n.rm_link(self.dpid, sw_dpid)

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
        self.sw.connection.addListeners(self)       # This binds our PacketIn event listener
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
        self.sw.add_host(packet.src, packet_in.in_port) # only unique is added
        log.warning("{0}:handling packet src:{1} dst:{2}".format(dpid_to_str(self.sw.dpid), packet.src, packet.dst))
        self.sw.n.handle_HostEvent(event)

    def _handle_LinkEvent(self, event):
        l = event.link
        # only handle this event if we are involved
        if not self.sw.dpid in (l.dpid1, l.dpid2):
            return

        # only handle the event if we are the controller for either of them
        if not (self.sw.n.ctrl_by_me(l.dpid1) or self.sw.n.ctrl_by_me(l.dpid2)):
            return

        if event.added:
            # determine the uplink port and save it
            if l.dpid1 == self.sw.dpid:
                self.sw.add_uplink(l.port1, l.dpid2, l.port2)
            else:
                self.sw.add_uplink(l.port2, l.dpid1, l.port1)
        else:
            # Link down event
            if l.dpid1 == self.sw.dpid:
                self.sw.rm_uplink(l.port1, l.dpid2)
            else:
                self.sw.rm_uplink(l.port2, l.dpid1)
                
        # let the controller handle it now
        self.sw.n.handle_LinkEvent(event)
        log.debug("Link {0} event on {1}: link {2}:{3} to {4}:{5}".format(event.added, self.sw.dpid, l.dpid1, l.port1, l.dpid2, l.port2))


class SPFNetwork(object):

    def __init__(self, *args, **kwargs):
        self.controllerID = 0
        self.controllers = {}
   
    def add_switch(self, id_):
        G.add_node(id_, tp="switch")
        self.redraw()

    def add_host(self, id_):
        G.add_node(id_, tp="host")
        self.redraw()

    def add_link(self, _from, _to, ports):
        G.add_edge(_from, _to, ports=ports)
        self.redraw()

    def rm_switch(self, id_):
        G.remove_node(id_)
        self.redraw()

    def rm_host(self, id_):
        G.remove_node(id_)
        self.redraw()

    def rm_link(self, _from, _to):
        try:
            G.remove_edge(_from, _to)
        except nx.NetworkXError as e:
            print(e)
            try:
                G.remove_edge(_to, _from)
            except nx.NetworkXError as e:
                print(e)
                return
        else:
            self.redraw()
    
    def path_recalc(self):
        for switch in G.nodes(data=True):
            if switch[1].get('tp') == "switch":
                if switches.get(switch[0]) and self.ctrl_by_me(switches[switch[0]].dpid): # only control the switches we need to control
                    log.debug("-- NEXT HOPS FOR SWITCH: {0}".format(switch[0]))
                    sw = switches[switch[0]]
                    for host in G.nodes(data=True):
                        if host[1].get('tp') == "host":
                            try:
                                path = nx.shortest_path(G, switch[0], host[0])
                            except nx.exception.NetworkXNoPath:
                                pass
                            else:
                                if len(path) > 1:
                                    if isinstance(path[1], EthAddr):
                                        log.debug("FROM {0} TO {1}: {2} via port {3}".format(switch[0], host[0], path[1], sw.neighbourtable[path[1]]))
                                        sw.add_flow(host[0], sw.neighbourtable[path[1]])
                                    else:
                                        # find the right/first uplink port to switch
                                        for k,v in sw.uplinkports.items():
                                            if v == path[1]:
                                                log.debug("FROM {0} TO {1}: {2} via uplink port {3}".format(switch[0], host[0], path[1], k))
                                                sw.add_flow(host[0], k)
                                                break
                log.debug("--")
    
    def redraw(self):
        plt.clf()
        colors = [colormap.get(node[1].get('tp', 'remoteswitch')) for node in G.nodes(data=True)]
        pos=nx.spring_layout(G)
        nx.draw_networkx_nodes(G,pos, node_color=colors)
        nx.draw_networkx_labels(G,pos)
        nx.draw_networkx_edges(G,pos)
        nx.draw_networkx_edge_labels(G, pos)
        plt.axis('off')
        plt.draw()
        plt.savefig('/tmp/net{0}.png'.format(self.controllerID))

    def ctrl_by_me(self, dpid):
        return dpid % (len(self.controllers)+1) == self.controllerID

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

class PyreNetworkController(SPFNetwork):
    
    def __init__(self, ID, *args, **kwargs):
        super(PyreNetworkController, self).__init__()
        self.controllerID = ID
        core.pyre.addListenerByName("PyreEvent", self.handle_PyreEvent)
    
    def handle_HostEvent(self, event):
        """
        Handle host changes
        """
        packet = event.parsed # This is the parsed packet data.
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp
        ev = ("H", event.dpid, packet.src, packet_in.in_port)
        core.pyre.shout("POX", pickle.dumps(ev, pickle.HIGHEST_PROTOCOL))
        self.path_recalc()
        
    def handle_LinkEvent(self, event):
        """
        Handle link event from switch we control
        """
        # recalculate flows
        ev = ( "S", event.added, event.link ) # LinkEvents are not serializable :(
        core.pyre.shout("POX", pickle.dumps(ev, pickle.HIGHEST_PROTOCOL))
        self.path_recalc()
    
    def handle_PyreEvent(self, ev):
        """
        Handle link event from switch we don't control
        """
        print("PYREEVENT", ev)
        if ev.type == "SHOUT":
            peer = ev.msg.pop(0)
            name = ev.msg.pop(0)
            grp = ev.msg.pop(0)
            event = pickle.loads(ev.msg.pop(0))
            #print(event)
            if event[0] == 'S':
                l = event[2]        
                if event[1]:
                    self.add_link(l.dpid1, l.dpid2, "{0}:{1}".format(l.port1, l.port2))
                else:
                    self.rm_link(l.dpid1, l.dpid2)
            elif event[0] == 'H':
                dpid = event[1]
                mac = event[2]
                port = event[3]
                self.add_host(mac)
                self.add_link(dpid, mac, port)
                    
            # recalculate flows
            self.path_recalc()
            return
        elif ev.type == "JOIN":
            ctrl_id = ev.msg.pop(0)
            ctrl_name = ev.msg.pop(0)
            grp_name = ev.msg.pop(0)
            if grp_name == "POX":
                self.controllers.update({ctrl_id : ctrl_name})
                # from now on switches are controlled using the updated list


def launch (id=0):
    """
    Starts the component
    """
    def start_switch (event):
        log.debug("Controlling {0}:{1}".format(event.connection,event.dpid))
        if N.ctrl_by_me(event.dpid):
            sw = switches.get(event.dpid)
            if sw is None:
                # New switch
                sw = Switch(event.dpid, event.connection, N)
                N.add_switch(event.dpid)
                switches[event.dpid] = sw
            else:
                log.warning("We already know switch {0}, setting new connection object".format(dpid_to_str(event.dpid)))
                sw.connection = event.connection

            SwitchHandler(sw)

    plt.ion()
    N = PyreNetworkController(int(id))
    core.openflow.addListenerByName("ConnectionUp", start_switch)


#if __name__ == "__main__":
    #N = SPFNetwork()
