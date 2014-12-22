import vdebug.connection
import vdebug.opts
import vdebug.util
import vim

class Listener:
    @classmethod
    def create(cls):
        if vdebug.opts.Options.get('background_listener', int):
            return BackgroundListener()
        else:
            return ForegroundListener()

class ForegroundListener:
    def __init__(self):
        self.__server = vdebug.connection.SocketCreator(vdebug.util.InputStream())

    def start(self):
        self.__server.start(vdebug.opts.Options.get('server'),
                            vdebug.opts.Options.get('port', int),
                            vdebug.opts.Options.get('timeout', int))

    def stop(self):
        self.__server.clear()

    def is_listening(self):
        return False

    def is_ready(self):
        return self.__server.has_socket()

    def status(self):
        return "inactive"

    def create_connection(self):
        handler = vdebug.connection.ConnectionHandler(*self.__server.socket())
        self.stop()
        return handler

class BackgroundListener:

    def __init__(self):
        self.__server = vdebug.connection.SocketServer()

    def start(self):
        self.__server.start(vdebug.opts.Options.get('server'),
                            vdebug.opts.Options.get('port', int))

    def stop(self):
        self.__server.stop()

    def status(self):
        if not self.__server:
            return "inactive"
        if self.is_ready():
            return "ready"
        elif self.__server.is_alive():
            return "listening"
        else:
            return "inactive"

    def is_ready(self):
        return self.__server.has_socket()

    def is_listening(self):
        return not self.is_ready() and self.__server.is_alive()

    def create_connection(self):
        handler = vdebug.connection.ConnectionHandler(*self.__server.socket())
        self.stop()
        return handler
