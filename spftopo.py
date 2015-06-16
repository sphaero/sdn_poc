#!/usr/bin/python

"""
This is a simple example that demonstrates multiple links
between nodes.
"""

from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSSwitch, Controller, RemoteController

def runMultiLink():
    "Create and run multiple link network"
    topo = simpleMultiLinkTopo( n=5 )
    net = Mininet( topo=topo, switch=OVSSwitch, controller=None, autoSetMacs=True, autoStaticArp=True )
    net.addController(RemoteController( 'c0', ip='192.168.12.50' ))
    net.staticArp()
    net.start()
    CLI( net )
    net.stop()

class simpleMultiLinkTopo( Topo ):
    "Spf topology"

    def __init__( self, n, **kwargs ):
        Topo.__init__( self, **kwargs )

        switches = []
        hosts = []

        for i in range(1,n+1):
            switches.append(self.addSwitch('s'+str(i)))

        for j in range(1,n+1):
            hosts.append(self.addHost('h'+str(j)))

        for k in range(n):
            self.addLink(switches[k], hosts[k])

        for l in range(n):
            self.addLink(switches[l], switches[(l+1)%n])

        for h in self.hosts():
            print(h, type(h))


if __name__ == '__main__':
    setLogLevel( 'info' )
    runMultiLink()

