import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

<<<<<<< HEAD
import dbgp
import vimui.ui
import vimui.window
=======
import dbgp.connection
import dbgp.api
import ui.vim.interface
>>>>>>> c84e819fb989abf0b4e830c44fd64f28c422ec0c

class Debugger:
    def __init__(self):
        self.ui = ui.vim.interface.Ui()

    def open(self,server='',port=9000,timeout=30):
        try:
            self.listen(server,port,timeout)
            self.ui.open()
<<<<<<< HEAD
        except dbgp.TimeoutError:
            self.ui.say("No connection was made")
=======
            addr = str(self.api.conn.address)
            self.ui.say("Found connection from "+addr)
            stat_response = self.api.status()
            self.ui.watchwin.write(stat_response.as_string())
        except dbgp.connection.TimeoutError:
>>>>>>> c84e819fb989abf0b4e830c44fd64f28c422ec0c
            self.close()
            self.ui.say("No connection was made")
        except:
            self.ui.error("An error occured: "+str(sys.exc_info()[0]))
            self.close()
            raise

    def listen(self,server,port,timeout):
        connection = dbgp.Connection(server,port,timeout)
        self.api = dbgp.Api(connection)

    def close(self):
        if self.api is not None:
            self.api.stop()
            self.api.conn.close()
            self.api = None
        self.ui.close()

vdebug = Debugger()
