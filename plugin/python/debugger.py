import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import dbgp
import log
import ui.vimui
import vim

class Debugger:
    """ Class that stitches together all the debugger components.

    This instantiates the connection and debugger UI, and provides
    an interface that Vim can use to send commands.
    """

    def __init__(self):
        self.ui = ui.vimui.Ui()
        self.api = None

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

    def is_alive(self):
        if self.api is not None and \
            self.api.conn.isconnected():
                return True
        return False

    def run(self):
        try:
            if not self.is_alive():
                self.open()
                status = self.api.status()
                self.ui.statuswin.set_status(status)
            else:
                self.api.run()
                status = self.api.status()
                self.ui.statuswin.set_status(status)

        except dbgp.TimeoutError:
            self.close()
            self.ui.say("No connection was made")
        except EOFError:
            self.ui.say("Connection to the debugger has been broken")
        except vim.error, e:
            self.ui.error(e)
        except:
            self.ui.error("An error occured: "+str(sys.exc_info()[0]))
            self.close()
            raise


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
