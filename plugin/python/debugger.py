import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import dbgp
import log
import ui.vimui
import vim
import breakpoint

class Debugger:

    def __init__(self):
        self.runner = Runner()

    def handle_timeout(self):
        self.runner.close()
        self.runner.ui.say("No connection was made")

    def handle_socket_end(self):
        self.runner.ui.say("Connection to the debugger has been broken")

    def run(self):
        try:
            self.runner.run()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.runner.ui.error(e)
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0]))
            self.runner.close()
            raise

    def add_breakpoint(self,args = None):
        try:
            self.runner.add_breakpoint(args)
        except breakpoint.WrongWindowError:
            self.ui.say("Breakpoints must be assigned in the " + \
                    "source code window")
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.runner.ui.error(e)
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0]))
            self.runner.close()
            raise

    def close(self):
        self.runner.close()

    
class Runner:
    """ Class that stitches together all the debugger components.

    This instantiates the connection and debugger UI, and provides
    an interface that Vim can use to send commands.
    """

    def __init__(self):
        self.ui = ui.vimui.Ui()
        self.api = None
        self.breakpoints = breakpoint.Store()

    def open(self,server='',port=9000,timeout=30):
        """ Open the connection and debugging UI.

        If either of these are already open, the current
        connection or UI is used.
        """
        self.listen(server,port,timeout)
        self.ui.open()
        addr = str(self.api.conn.address)
        log.Log("Found connection from " + addr,log.Logger.INFO)
        self.ui.sourcewin.set_file(self.api.startfile)
        self.ui.sourcewin.place_pointer(1)
        self.breakpoints.link_api(self.api)

    def do(self,command):
        pass

    def is_alive(self):
        if self.api is not None and \
            self.api.conn.isconnected():
                return True
        return False

    def run(self):
        if not self.is_alive():
            self.open()
            status = self.api.status()
            self.ui.statuswin.set_status(status)
        else:
            self.api.run()
            status = self.api.status()
            self.ui.statuswin.set_status(status)

    def add_breakpoint(self,args):
        bp = breakpoint.Breakpoint.parse(self.ui,args)
        if bp.type == "line":
            id = self.breakpoints.find_breakpoint(\
                    bp.get_file(),\
                    bp.get_line())
            if id is not None:
                self.breakpoints.remove_breakpoint_by_id(id)
                return
        self.breakpoints.add_breakpoint(bp)

    def listen(self,server,port,timeout):
        """ Open the dbgp API with connection.

        Uses existing connection if possible.
        """
        if self.is_alive():
            log.Log("Cannot open a new connection \
                while one already exists",\
                log.Logger.ERROR)
            return
        else:
            connection = dbgp.Connection(server,port,timeout)
            self.api = dbgp.Api(connection)

    def close_connection(self):
        """ Close the connection to the debugger.
        """
        try:
            if self.is_alive():
                self.breakpoints.unlink_api()
                self.api.stop()
                self.api.conn.close()
            self.api = None
        except EOFError:
            self.ui.say("Connection has been closed")

    def close(self):
        """ Close both the connection and UI.
        """
        self.close_connection()
        self.ui.close()

vdebug = Debugger()
