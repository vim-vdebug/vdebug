if __name__ == "__main__":
    import sys
    sys.path.append('../plugin/python/')
import unittest2 as unittest
import vdebug.dbgp

class SocketMockError():
    pass

class SocketMock():
    def __init__(self):
        self.response = []
        self.last_msg = None
        self.timeouts = []
        self.exception = None

    def recv(self,length):
        if(self.exception != None):
            raise self.exception
        ret = self.response[0]
        if len(ret) >= length:
            chars = ret[0:length]
            newval = ret[length:]
            if len(newval) > 0:
                self.response[0] = newval
            else:
                self.response.pop(0)
            return "".join(chars)
        else:
            self.response.pop(0)
            return ''

    def add_response(self,res):
        res = str(res)
        self.response.append(list(res))
        self.response.append(['\0'])

    def add_raise(self,exception):
        self.exception = exception

    def send(self,msg):
        self.last_msg = msg

    def settimeout(self,timeout):
        self.timeouts.append(timeout)

    def get_last_sent(self):
        return self.last_msg

    def get_timeouts(self):
        return self.timeouts

    def close(self):
        pass


class ConnectionTest(unittest.TestCase):      

    def setUp(self):
        self.conn = vdebug.dbgp.Connection('', 0)
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
    Test that the recv_msg method sets, and then clears the timeout.
    """
    def test_timeout(self):
        self.conn.sock.add_response(3)
        self.conn.sock.add_response('foo')
        self.conn.sock.add_response('\0')

        response = self.conn.recv_msg(1)
        assert self.conn.sock.get_timeouts()[0] == 1
        assert self.conn.sock.get_timeouts()[1] == None

    """
    Test that the recv_msg method clears the timeout even if there is a raise.
    """
    def test_timeout_finally(self):
        self.conn.sock.add_raise(SocketMockError())

        try:
            response = self.conn.recv_msg(1)
            assert False
        except:
            pass
        assert self.conn.sock.get_timeouts()[1] == None

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

