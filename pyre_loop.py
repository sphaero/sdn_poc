"""
These are example uses of the recoco cooperative threading library. Hopefully
they will save time for developers getting used to the POX environment.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.recoco import *

from pyre import Pyre
import zmq

log = core.getLogger()

class PyreEvent(Event):
    """
    Pyre Event
    * type: WHISPER or SHOUT
    * message: list of remaining messages
    """
    def __init__(self, t, msg):
        Event.__init__(self)
        self.type = t
        self.msg = msg

class PyreEventLoop(EventMixin, Task):
    """
    Component that implements a Pyre(Zyre) process
    
    Sends out PyreEvents
    """
    
    _core_name = "pyre"
    _eventMixin_events = set([
            PyreEvent,
        ])
    
    def __init__(self):
        Task.__init__(self)  # call our superconstructor
        
        self.n = Pyre("POX")
        self.n.join("CHAT")
        
        self.sockets = self.get_sockets() # ... the sockets to listen to events on

        # Note! We can't start our event loop until the core is up. Therefore,
        # we'll add an event handler.
        core.addListener(pox.core.GoingUpEvent, self.start_event_loop)

    def start_event_loop(self, event):
        """
        Takes a second parameter: the GoingUpEvent object (which we ignore)
        """
        # This causes us to be added to the scheduler's recurring Task queue
        self.n.start()
        Task.start(self)
        print("TASK STARTED")
        self.raiseEvent(PyreEvent,"WHISPER", "bla")

    def get_sockets(self):
        return [self.n.inbox.getsockopt(zmq.FD)]

    def handle_read_events(self):
        while self.n.inbox.getsockopt(zmq.EVENTS) & zmq.POLLIN == zmq.POLLIN:
            cmds = self.n.recv()
            print("READ EV:", cmds)
            t = cmds.pop(0)
            self.raiseEvent(PyreEvent,t, cmds)
#        return EventHalt

    def run(self):
        """
        run() is the method that gets called by the scheduler to execute this task
        """
        while core.running:
            """
            This looks almost exactly like python's select.select, except that it's
            it's handled cooperatively by recoco

            The only difference in Syntax is the "yield" statement, and the
            capital S on "Select"
            """
            try:
                rlist,wlist,elist = yield Select(self.sockets, [], [], 3)
                events = []
                for read_sock in rlist:
                    if read_sock in self.sockets:
                        events.append(read_sock)
            except Exception as e:
                print("EXCEPTION", e)
                break

            if events:
                self.handle_read_events() # ...
        print("STOP Pyre")
        self.n.stop()


def launch ():
    core.registerNew(PyreEventLoop)
    #a = PyreEventLoop()
