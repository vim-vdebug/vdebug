import unittest
import vdebug.connection

class SocketMockError():
    pass

class SocketMock():
    def __init__(self):
        self.response = []
        self.last_msg = []

    def recv(self,length):
        ret = self.response[0]
        if len(ret) >= length:
            chars = ret[0:length]
            newval = ret[length:]
            if len(newval) > 0:
                self.response[0] = newval
            else:
                self.response.pop(0)
            if (length == 1):
                return b"".join(chars)
            else :
                return b''.join(chars)
            #if type(chars[0]) is int:
            #    print("len same as length")
            #    print(ret[0:length])
            #    return b''.join([bytes(i) for i in chars])
            #    return b"".join(chars)
            #else:
            #    return b"".join(chars)
        else:
            self.response.pop(0)
            return b''

    def add_response(self,res):
        digitlist = []
        for i in str(res):
            digitlist.append(bytes(i, "utf8"))
        self.response.append(digitlist)

        #res = bytes(res, 'utf8')
        #self.response.append(list(res))
        self.response.append([b'\x00'])

    def send(self,msg):
        self.last_msg.append( msg )
        return len(msg)

    def get_last_sent(self):
        last = self.last_msg
        self.last_msg = [];
        return b''.join(last).decode('UTF-8')

    def close(self):
        pass


class ConnectionTest(unittest.TestCase):

    def setUp(self):
        self.conn = vdebug.connection.ConnectionHandler('', 0)
        self.conn.sock = SocketMock()

    """
    Test that the recv_msg method reads from the socket object.

    The socket's recv() method is called for three purposes
        1. Message length
        2. Message body
        3. A finishing null byte
    """
    def test_read(self):
        self.conn.sock.add_response(3)
        self.conn.sock.add_response('foo')
        self.conn.sock.add_response('\0')

        response = self.conn.recv_msg()
        assert response == 'foo'

    """
    Test a longer read.
    """
    def test_read_long(self):
        self.conn.sock.add_response(24)
        self.conn.sock.add_response('this is a longer message')
        self.conn.sock.add_response('\0')

        response = self.conn.recv_msg()
        assert response == 'this is a longer message'

    """
    Test that an EOFError is raised if the socket appears to be closed.
    """
    def test_read_eof(self):
        self.conn.sock.add_response('')
        self.assertRaises(EOFError,self.conn.recv_msg)

    """
    Test that the send_msg command calls send on the socket,
    and adds a null byte to the string.
    """
    def test_send(self):
        cmd = 'this is a cmd'
        self.conn.send_msg(cmd)
        sent = self.conn.sock.get_last_sent()
        assert sent == cmd+'\0'
