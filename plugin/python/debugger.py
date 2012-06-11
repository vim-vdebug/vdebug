import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import dbgp.connection
import dbgp.api

class Debugger:
    def open(self,server='',port=9000,timeout=30):
        self.listen(server,port,timeout)

    def listen(self,server,port,timeout):
        connection = dbgp.connection.Connection(server,port,timeout)
        self.api = dbgp.api.Api(connection)

    def close(self):
        self.api.stop()
        self.api.conn.close()

vdebug = Debugger()
