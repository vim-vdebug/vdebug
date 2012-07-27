import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import dbgp.connection
import dbgp.api
import vimui.ui
import vimui.window

class Debugger:
    def __init__(self):
        self.ui = vimui.ui.Ui()

    def open(self,server='',port=9000,timeout=30):
        try:
            self.listen(server,port,timeout)
            self.ui.open()
        except dbgp.connection.TimeoutError:
            self.ui.say("No connection was made")
            self.close()
        except Exception, e:
            self.ui.say("An error occured: "+str(sys.exc_info()[0]))
            self.close()
            raise e

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
