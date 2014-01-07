import socket
import sys
import os
import Queue
import threading
import vdebug.log

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
        vdebug.log.Log("Closing the socket",\
                        vdebug.log.Logger.DEBUG)
        self.sock.close()

    def __recv_length(self):
        """Get the length of the proceeding message."""
        length = ''
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError('Socket Closed')
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
                raise EOFError('Socket Closed')
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
                raise EOFError('Socket Closed')
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

class BackgroundSocketCreator(threading.Thread):
    def __init__(self, host, port, message_q, output_q):
        self.__message_q = message_q
        self.__output_q = output_q
        self.__host = host
        self.__port = port
        threading.Thread.__init__(self)
        self.__log = open('queueserver.log','w')

    def log(self, message):
        self.__log.write(message+"\n")
        self.__log.flush()

    def run(self):
        self.log("Started")
        self.log("Listening on port %s" % self.__port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(0)
            s.bind((self.__host, self.__port))
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
        except Exception:
            self.log("Error: %s" % str(sys.exc_info()))
            self.log("Stopping server")
        finally:
            self.__shutdown(s)

    def __shutdown(self, server):
        server.close()
        self.__log.close()

    def __peek_for_exit(self):
        try:
            #self.log("Checking for exit")
            self.__check_exit(self.__message_q.get_nowait())
        except Queue.Empty:
            pass

    def __check_exit(self, message):
         if message == "exit":
            raise Exception("Exiting")

class SocketServer:
    def __init__(self):
        self.__message_q = Queue.Queue(0)
        self.__socket_q = Queue.Queue(0)
        self.__sock = None
        self.__thread = None

    def __del__(self):
        self.stop()

    def start(self, host, port):
        if not self.is_alive():
            self.__thread = BackgroundSocketCreator(host,
                                                    port,
                                                    self.__message_q,
                                                    self.__socket_q)
            self.__thread.start()
            print "Started queue server thread"

    def is_alive(self):
        return self.__thread and self.__thread.is_alive()

    def status(self):
        if self.is_alive():
            print "Running"
        else:
            print "Stopped"

    def socket(self):
        if not self.__sock:
            try:
                self.__sock = self.__socket_q.get_nowait()
            except Queue.Empty:
                pass
        return self.__sock

    def stop(self):
        if self.is_alive():
            #print "Sending exit message"
            self.__message_q.put_nowait("exit")
            #print "Joining threads"
            self.__thread.join(3000)
            #print "Stopped"
