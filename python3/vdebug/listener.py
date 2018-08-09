import vim

from . import connection
from . import opts
from . import util


class Listener:

    @classmethod
    def create(cls):
        if opts.Options.get('background_listener', int):
            return BackgroundListener()
        return ForegroundListener()


class ForegroundListener:

    def __init__(self):
        self.__server = connection.SocketCreator(util.InputStream())

    def start(self):
        self.__server.start(opts.Options.get('server'),
                            opts.Options.get('port', int),
                            opts.Options.get('timeout', int))

    def stop(self):
        self.__server.clear()

    def is_listening(self):
        return False

    def is_ready(self):
        return self.__server.has_socket()

    def status(self):
        return "inactive"

    def create_connection(self):
        handler = connection.ConnectionHandler(*self.__server.socket())
        self.stop()
        return handler


class BackgroundListener:

    def __init__(self):
        self.__server = connection.SocketServer()

    def start(self):
        if opts.Options.get("auto_start", int):
            vim.command('autocmd Vdebug CursorHold,CursorHoldI,CursorMoved,CursorMovedI,FocusGained,FocusLost * python3 debugger.start_if_ready()')
        self.__server.start(opts.Options.get('server'),
                            opts.Options.get('port', int))

    def stop(self):
        if opts.Options.get("auto_start", bool):
            vim.command('augroup Vdebug')
            vim.command('autocmd!')
            vim.command('augroup END')
        self.__server.stop()

    def status(self):
        if not self.__server:
            return "inactive"
        if self.is_ready():
            return "ready"
        if self.__server.is_alive():
            return "listening"
        return "inactive"

    def is_ready(self):
        return self.__server.has_socket()

    def is_listening(self):
        return not self.is_ready() and self.__server.is_alive()

    def create_connection(self):
        handler = connection.ConnectionHandler(*self.__server.socket())
        self.stop()
        return handler
