import socket

class Connection:
    """ DBGP connection class """
    def __init__(self, host = '', port = 9000, timeout = 30):
        self.port = 9000
        self.sock = None
        self.host = host
        self.timeout = timeout
        self.isconned = 0
    def isconnected(self):
        return self.isconned
    def open(self):
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

        print 'Found connection from ', address
        self.isconned = 1
        serv.close()
    def close(self):
        if self.sock != None:
            self.sock.close()
            self.sock = None
        self.isconned = 0
    def recv_length(self):
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
    def recv_null(self):
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError, 'Socket Closed'
            if c == '\0':
                return
    def recv_body(self, to_recv):
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
        length = self.recv_length()
        body     = self.recv_body(length)
        self.recv_null()
        return body
    def send_msg(self, cmd):
        self.sock.send(cmd + '\0')
