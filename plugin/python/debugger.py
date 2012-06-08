import dbgp.connection
import dbgp.interface

class Debugger:
    def listen(self,server='',port=9000,timeout=30):
        connection = dbgp.connection.Connection(server,port,timeout)
        self.interface = dbgp.interface.Interface(connection)

dbg = Debugger()
