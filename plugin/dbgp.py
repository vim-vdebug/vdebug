import socket

"""This module provides classes for speaking with debuggers that use the DBGP protocol.

These classes are language independent, and can be used without external modules.
"""

class Connection:
    """DBGP connection class, for managing the connection to the debugger.

    The host, port and socket timeout are configurable on object construction.
    """

    sock = None
    isconned = 0

    def __init__(self, host = '', port = 9000, timeout = 30):
        """Create a new Connection.

        The connection is not established until open() is called.

        host -- host name where debugger is running (default '')
        port -- port number which debugger is listening on (default 9000)
        timeout -- time in seconds to wait for a debugger connection before giving up (default 30)
        """
        self.port = 9000
        self.host = host
        self.timeout = timeout

    def __del__(self):
        """Make sure the connection is closed."""
        self.close()

    def isconnected(self):
        """Whether the connection has been established."""
        return self.isconned

    def open(self):
        """Listen for a connection from the debugger.

        The socket is blocking, and it will wait for the length of
        time given by the timeout (default is 30 seconds).
        """
        print 'Waiting for a connection (this message will self-destruct in ',self.timeout,' seconds...)'
        serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serv.settimeout(self.timeout)
            serv.bind((self.host, self.port))
            serv.listen(5)
            (self.sock, address) = serv.accept()
            self.sock.settimeout(None)
        except socket.timeout, e:
            serv.close()
            self.stop()
            raise e

        print 'Found connection from', address
        self.isconned = 1
        serv.close()

    def close(self):
        """Close the connection."""
        if self.sock != None:
            self.sock.close()
            self.sock = None
        self.isconned = 0

    def __recv_length(self):
        """Get the length of the proceeding message."""
        length = ''
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError, 'Socket Closed'
            if c == '\0':
                return int(length)
            if c.isdigit():
                length = length + c

    def __recv_null(self):
        """Receive a null byte."""
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError, 'Socket Closed'
            if c == '\0':
                return

    def __recv_body(self, to_recv):
        """Receive a message of a given length.

        to_recv -- length of the message to receive
        """
        body = ''
        while to_recv > 0:
            buf = self.sock.recv(to_recv)
            if buf == '':
                self.close()
                raise EOFError, 'Socket Closed'
            to_recv -= len(buf)
            body = body + buf
        return body

    def recv_msg(self):
        """Receive a message from the debugger.
        
        Returns a string, which is expected to be XML.
        """
        length = self.__recv_length()
        body     = self.__recv_body(length)
        self.__recv_null()
        return body

    def send_msg(self, cmd):
        """Send a message to the debugger.

        cmd -- command to send
        """
        self.sock.send(cmd + '\0')

class Protocol:
    """Interface for DBGP commands.

    Uses a Connection object to read and write with the debugger,
    and builds commands and returns the results.
    """

    conn = None
    transID = 0

    def __init__(self,connection):
        """Create a new Protocol using a Connection object.

        The Connection object specifies the debugger connection,
        and the Protocol provides a OO interface to interacting
        with it.

        connection -- The Connection object to use
        """
        self.conn = connection
        if self.conn.isconnected == 0:
            self.conn.open()
        self.init_msg = self.conn.recv_msg()

    def send_cmd(self,cmd,args = ''):
        """Send a command to the debugger.

        This method automatically adds a unique transaction ID to the command,
        which is required by the debugger.

        cmd -- the command name, e.g. 'status'
        args -- arguments for the command, which is optional for certain commands (default '')
        """
        args = args.strip()
        cmd = cmd.strip()
        self.transID += 1
        cmd += ' -i '+ str(self.transID)
        if len(args) > 0:
            cmd += ' ' + args
        print "Command: ",cmd
        self.conn.send_msg(cmd)
        return self.conn.recv_msg()

    def status(self):
        """Get the debugger status."""
        return self.send_cmd('status')
