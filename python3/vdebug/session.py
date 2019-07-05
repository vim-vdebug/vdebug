import socket

import vim

from . import dbgp
from . import error
from . import event
from . import listener
from . import log
from . import opts
from . import util


class SessionHandler:

    def __init__(self, ui, breakpoints):
        self.__ui = ui
        self.__breakpoints = breakpoints
        self.__ex_handler = util.ExceptionHandler(self)
        self.__session = None
        self.listener = None

    def dispatch_event(self, name, *args):
        event.Dispatcher(self).dispatch_event(name, *args)

    def ui(self):
        return self.__ui

    def breakpoints(self):
        return self.__breakpoints

    def session(self):
        return self.__session

    def listen(self):
        if self.listener and self.listener.is_listening():
            print("Waiting for a connection: none found so far")
        elif self.listener and self.listener.is_ready():
            print("Found connection, starting debugger")
            self.__new_session()
        else:
            self.start_listener()

    def start_listener(self):
        self.listener = listener.Listener.create()
        print("Vdebug will wait for a connection in the background")
        util.Environment.reload()
        if self.is_open():
            self.ui().set_status("listening")
        self.listener.start()
        self.start_if_ready()

    def stop_listening(self):
        if self.listener:
            self.listener.stop()
            self.ui().say("Vdebug stopped waiting for a connection")

        if self.__session:
            self.__session.close_connection()

    def run(self):
        if self.is_connected():
            self.dispatch_event("run")
        else:
            self.listen()

    def stop(self):
        if self.is_connected():
            self.__session.close_connection()
        elif self.is_listening():
            self.stop_listening()
        elif self.is_open():
            self.__ui.close()
        else:
            self.__ui.say("Vdebug is not running")

    def close(self):
        self.stop_listening()
        if self.is_connected():
            self.__session.close_connection()
        if self.is_open():
            self.__ui.close()

    def is_connected(self):
        return self.__session and self.__session.is_connected()

    def is_listening(self):
        return self.listener and self.listener.is_listening()

    def is_open(self):
        return self.__ui.is_open

    def status(self):
        if self.is_connected():
            return "running"
        return self.listener.status()

    def status_for_statusline(self):
        return "vdebug(%s)" % self.status()

    def start_if_ready(self):
        try:
            if self.listener.is_ready():
                print("Found connection, starting debugger")
                self.__new_session()
                return True
            return False
        except Exception as e:
            print("Error starting Vdebug: %s" %
                  self.__ex_handler.exception_to_string(e))

    def __new_session(self):
        log.Log("create session", log.Logger.DEBUG)
        self.__session = Session(self.__ui, self.__breakpoints,
                                 util.Keymapper())

        log.Log("start session", log.Logger.DEBUG)
        status = self.__session.start(self.listener.create_connection())
        log.Log("refresh event", log.Logger.DEBUG)
        self.dispatch_event("refresh", status)


class Session:

    def __init__(self, ui, breakpoints, keymapper):
        self.__ui = ui
        self.__breakpoints = breakpoints
        self.__keymapper = keymapper
        self.__api = None
        self.cur_file = None
        self.cur_lineno = None
        self.context_names = None

    def api(self):
        return self.__api

    def keymapper(self):
        return self.__keymapper

    def is_connected(self):
        return self.__api is not None

    def is_open(self):
        return self.__ui.is_open

    def ui(self):
        return self.__ui

    def close(self):
        """ Close both the connection and vdebug.ui.
        """
        self.close_connection()
        self.__ui.close()
        self.__keymapper.unmap()

    def close_connection(self, stop=True):
        """ Close the connection to the debugger.
        """
        self.__ui.mark_as_stopped()
        try:
            if self.is_connected():
                log.Log("Closing the connection")
                if stop:
                    if opts.Options.get('on_close') == 'detach':
                        try:
                            self.__api.detach()
                        except dbgp.CmdNotImplementedError:
                            self.__ui.error('Detach is not supported by the '
                                            'debugger, stopping instead')
                            opts.Options.overwrite('on_close', 'stop')
                            self.__api.stop()
                    else:
                        self.__api.stop()
                self.__api.conn.close()
                self.__api = None
                self.__breakpoints.unlink_api()
            else:
                self.__api = None
                self.__breakpoints.unlink_api()
        except EOFError:
            self.__api = None
            self.__ui.say("Connection has been closed")
        except socket.error:
            self.__api = None
            self.__ui.say("Connection has been closed")

    def start(self, connection):
        util.Environment.reload()
        if self.__ui.is_modified():
            raise error.ModifiedBufferError("Modified buffers must be saved "
                                            "before debugging")

        try:
            self.__api = dbgp.Api(connection)
            if not self.is_open():
                self.__ui.open()
                self.__keymapper.map()

            self.__ui.set_listener_details(opts.Options.get('server'),
                                           opts.Options.get('port'),
                                           opts.Options.get('ide_key'))

            addr = self.__api.conn.address
            log.Log("Found connection from %s" % str(addr), log.Logger.INFO)
            self.__ui.set_conn_details(addr[0], addr[1])

            self.__collect_context_names()
            self.__set_features()
            self.__initialize_breakpoints()

            if opts.Options.get('break_on_open', int) == 1:
                log.Log('starting with step_into (break_on_open = 1)', log.Logger.DEBUG)
                status = self.__api.step_into()
            else:
                log.Log('starting with run (break_on_open = 0)', log.Logger.DEBUG)
                status = self.__api.run()
            return status
        except Exception:
            self.close()
            raise

    def detach(self):
        """Detach the debugger engine, and allow it to continue execution.
        """
        if self.is_connected():
            self.__ui.say("Detaching the debugger")
            self.__api.detach()

        self.close_connection(False)

    def __set_features(self):
        """Evaluate vim dictionary of features and pass to debugger.

        Errors are caught if the debugger doesn't like the feature name or
        value. This doesn't break the loop, so multiple features can be set
        even in the case of an error."""
        features = vim.eval('g:vdebug_features')
        for name, value in features.items():
            try:
                self.__api.feature_set(name, value)
            except dbgp.DBGPError as e:
                error_str = "Failed to set feature %s: %s" % (name, e.args[0])
                self.__ui.error(error_str)

    def __initialize_breakpoints(self):
        self.__breakpoints.update_lines(
            self.__ui.get_breakpoint_sign_positions())
        self.__breakpoints.link_api(self.__api)

    def __collect_context_names(self):
        cn_res = self.__api.context_names()
        self.context_names = cn_res.names()
        log.Log("Available context names: %s" % self.context_names,
                log.Logger.DEBUG)
