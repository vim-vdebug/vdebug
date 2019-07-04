import errno
import queue
import socket
import sys
import threading
import time

from . import log


class ConnectionHandler:
    """Handles read and write operations to a given socket."""

    def __init__(self, socket, address):
        """Accept the socket used for reading and writing.

        socket -- the network socket
        """
        self.sock = socket
        self.address = address

    def __del__(self):
        """Make sure the connection is closed."""
        self.close()

    def isconnected(self):
        return 1

    def close(self):
        """Close the connection."""
        log.Log("Closing the socket", log.Logger.DEBUG)
        self.sock.close()

    def __recv_length(self):
        """Get the length of the proceeding message."""
        length = []
        while 1:
            c = self.sock.recv(1)
            if c == b'':
                self.close()
                raise EOFError('Socket Closed')
            if c == b'\x00':
                return int(b''.join(length))
            if c.isdigit():
                length.append(c)

    def __recv_null(self):
        """Receive a null byte."""
        while 1:
            c = self.sock.recv(1)
            if c == b'':
                self.close()
                raise EOFError('Socket Closed')
            if c == b'\x00':
                return

    def __recv_body(self, to_recv):
        body = []
        while to_recv > 0:
            buf = self.sock.recv(to_recv)
            if buf == b'':
                self.close()
                raise EOFError('Socket Closed')
            to_recv -= len(buf)
            body.append(buf.decode("utf-8"))
        return ''.join(body)

    def recv_msg(self):
        """Receive a message from the debugger.

        Returns a string, which is expected to be XML.
        """
        length = self.__recv_length()
        body = self.__recv_body(length)
        self.__recv_null()
        return body

    def send_msg(self, cmd):
        """Send a message to the debugger.

        cmd -- command to send
        """
        #self.sock.send(cmd + '\0')
        MSGLEN = len(cmd)
        totalsent = 0
        while totalsent < MSGLEN:
            sent = self.sock.send(bytes(cmd[totalsent:].encode()))
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + sent
        sent = self.sock.send(b'\x00')


class SocketCreator:

    def __init__(self, input_stream=None):
        """Create a new Connection.

        The connection is not established until open() is called.

        input_stream -- object for checking input stream and user interrupts (default None)
        """
        self.__sock = None
        self.input_stream = input_stream

    def start(self, host='', port=9000, timeout=30):
        """Listen for a connection from the debugger. Listening for the actual
        connection is handled by self.listen()

        host -- host name where debugger is running (default '')
        port -- port number which debugger is listening on (default 9000)
        timeout -- time in seconds to wait for a debugger connection before giving up (default 30)
        """
        print('Waiting for a connection (Ctrl-C to cancel, this message will '
              'self-destruct in ', timeout, ' seconds...)')
        serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serv.setblocking(1)
            serv.bind((host, port))
            serv.listen(5)
            self.__sock = self.listen(serv, timeout)
        except socket.timeout:
            raise TimeoutError("Timeout waiting for connection")
        finally:
            serv.close()

    def listen(self, serv, timeout):
        """Non-blocking listener. Provides support for keyboard interrupts from
        the user. Although it's non-blocking, the user interface will still
        block until the timeout is reached.

        serv -- Socket server to listen to.
        timeout -- Seconds before timeout.
        """
        start = time.time()
        while True:
            if (time.time() - start) > timeout:
                raise socket.timeout
            try:
                """Check for user interrupts"""
                if self.input_stream is not None:
                    self.input_stream.probe()
                return serv.accept()
            except socket.error:
                pass

    def clear(self):
        self.__sock = None

    def socket(self):
        return self.__sock

    def has_socket(self):
        return self.__sock is not None


class BackgroundSocketCreator(threading.Thread):

    def __init__(self, host, port, message_q, output_q):
        self.__message_q = message_q
        self.__output_q = output_q
        self.__host = host
        self.__port = port
        threading.Thread.__init__(self)

    @staticmethod
    def log(message):
        log.Log(message, log.Logger.DEBUG)

    def run(self):
        self.log("Started")
        self.log("Listening on port %s" % self.__port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.__host, self.__port))
            s.settimeout(5) # timeout after 5 seconds so we can check messages
            s.listen(5)
            while 1:
                try:
                    self.__peek_for_exit()
                    client, address = s.accept()
                    self.log("Found client, %s" % str(address))
                    self.__output_q.put((client, address))
                    break
                except socket.error:
                    # No connection
                    pass
        except socket.error as socket_error:
            self.log("Error: %s" % str(sys.exc_info()))
            self.log("Stopping server")

            if socket_error.errno == errno.EADDRINUSE:
                self.log("Address already in use")
                print("Socket is already in use")
        except Exception:
            print("Exception caught")
            self.log("Error: %s" % str(sys.exc_info()))
            self.log("Stopping server")
        finally:
            self.log("Finishing socket server")
            s.close()

    def __peek_for_exit(self):
        try:
            # self.log("Checking for exit")
            self.__check_exit(self.__message_q.get_nowait())
        except queue.Empty:
            pass

    @staticmethod
    def __check_exit(message):
        if message == "exit":
            raise Exception("Exiting")


class SocketServer:

    def __init__(self):
        self.__message_q = queue.Queue(0)
        self.__socket_q = queue.Queue(1)
        self.__thread = None

    def __del__(self):
        self.stop()

    def start(self, host, port):
        if not self.is_alive():
            self.__thread = BackgroundSocketCreator(
                host, port, self.__message_q, self.__socket_q)
            self.__thread.start()

    def is_alive(self):
        return self.__thread and self.__thread.is_alive()

    def has_socket(self):
        return self.__socket_q.full()

    def socket(self):
        return self.__socket_q.get_nowait()

    def stop(self):
        if self.is_alive():
            self.__message_q.put_nowait("exit")
            self.__thread.join(3000)
        if self.has_socket():
            self.socket()[0].close()
