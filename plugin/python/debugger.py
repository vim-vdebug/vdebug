import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import dbgp.connection
import dbgp.api
import ui.vim.interface

class Debugger:
    def __init__(self):
        self.ui = ui.vim.interface.Ui()

    def open(self,server='',port=9000,timeout=30):
        try:
            self.listen(server,port,timeout)
            self.ui.open()
            addr = str(self.api.conn.address)
            self.ui.say("Found connection from "+addr)
            stat_response = self.api.status()
            self.ui.watchwin.write(stat_response.as_string())
        except dbgp.connection.TimeoutError:
            self.close()
            self.ui.say("No connection was made")
        except:
            self.ui.error("An error occured: "+str(sys.exc_info()[0]))
            self.close()
            raise

    def listen(self,server,port,timeout):
        connection = dbgp.connection.Connection(server,port,timeout)
        self.api = dbgp.api.Api(connection)

    def close(self):
        if self.api is not None:
            self.api.stop()
            self.api.conn.close()
            self.api = None
        self.ui.close()

vdebug = Debugger()
