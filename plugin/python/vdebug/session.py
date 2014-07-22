import vdebug.util
import vdebug.opts
import vdebug.log
import vdebug.dbgp
import vdebug.listener
import vim

class ModifiedBufferError(Exception):
    pass

class NoConnectionError(Exception):
    pass

class SessionHandler:
    def __init__(self, ui, breakpoints):
        self.__ui = ui
        self.__breakpoints = breakpoints
        self.__ex_handler = vdebug.util.ExceptionHandler(self)
        self.__session = None
        self.listener = None

    def dispatch_event(self, name, *args):
        vdebug.event.Dispatcher(self).dispatch_event(name, *args)

    def ui(self):
        return self.__ui

    def breakpoints(self):
        return self.__breakpoints

    def session(self):
        return self.__session

    def listen(self):
        if self.listener and self.listener.is_listening():
            print "Waiting for a connection: none found so far"
        elif self.listener and self.listener.is_ready():
            print "Found connection, starting debugger"
            self.__new_session()
        else:
            self.start_listener()

    def start_listener(self):
        self.listener = vdebug.listener.Listener.create()
        print "Vdebug will wait for a connection in the background"
        vdebug.util.Environment.reload()
        if self.is_open():
            self.ui().set_status("listening")
        self.listener.start()
        self.start_if_ready()

    def stop_listening(self):
        if self.listener:
            self.listener.stop()
            self.ui().say("Vdebug stopped waiting for a connection")

    def run(self):
        if self.is_connected():
            self.dispatch_event("run")
        else:
            self.listen()

    def stop(self):
        if self.is_connected():
            self.__session.close_connection()
        elif self.is_open():
            self.stop_listening()
            self.__ui.close()
        elif self.is_listening():
            self.listener.stop()
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
        else:
            return self.listener.status()

    def status_for_statusline(self):
        return "vdebug(%s)" % self.status()

    def start_if_ready(self):
        if self.listener.is_ready():
            print "Found connection, starting debugger"
            self.__new_session()
            return True
        else:
            return False

    def __new_session(self):
        self.__session = Session(self.__ui,
                self.__breakpoints,
                vdebug.util.Keymapper())

        status = self.__session.start(self.listener.create_connection())
        self.dispatch_event("refresh", status)

class Session:
    def __init__(self, ui, breakpoints, keymapper):
        self.__ui = ui
        self.__breakpoints = breakpoints
        self.__keymapper = keymapper
        self.__api = None
        self.cur_file = None
        self.cur_lineno = None

    def api(self):
        return self.__api

    def keymapper(self):
        return self.__keymapper

    def set_api(self, api):
        self.__api = api

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

    def close_connection(self, stop = True):
        """ Close the connection to the debugger.
        """
        self.__ui.mark_as_stopped()
        try:
            if self.is_connected():
                vdebug.log.Log("Closing the connection")
                if stop:
                    if vdebug.opts.Options.get('on_close') == 'detach':
                        try:
                            self.__api.detach()
                        except vdebug.dbgp.CmdNotImplementedError:
                            self.__ui.error('Detach is not supported by the debugger, stopping instead')
                            vdebug.opts.Options.overwrite('on_close', 'stop')
                            self.__api.stop()
                    else:
                        self.__api.stop()
                self.__api.conn.close()
                self.__api = None
            else:
                self.__api = None
        except EOFError:
            self.__api = None
            self.__ui.say("Connection has been closed")
        except socket.error:
            self.__api = None
            self.__ui.say("Connection has been closed")

    def start(self, connection):
        vdebug.util.Environment.reload()
        if self.__ui.is_modified():
            raise ModifiedBufferError("Modified buffers must be saved before debugging")

        try:
            self.__api = vdebug.dbgp.Api(connection)
            if not self.is_open():
                self.__ui.open()
                self.__keymapper.map()

            self.__ui.set_listener_details(\
                    vdebug.opts.Options.get('server'),\
                    vdebug.opts.Options.get('port'),\
                    vdebug.opts.Options.get('ide_key'))

            addr = self.__api.conn.address
            vdebug.log.Log("Found connection from %s" % str(addr), vdebug.log.Logger.INFO)
            self.__ui.set_conn_details(addr[0], addr[1])

            self.__collect_context_names()
            self.__set_features()
            self.__initialize_breakpoints()

            if vdebug.opts.Options.get('break_on_open', int) == 1:
                status = self.__api.step_into()
            else:
                status = self.__api.run()
            return status
        except Exception:
            self.close()
            raise

    def detach(self):
        """Detach the debugger engine, and allow it to continue execution.
        """
        self.__ui.say("Detaching the debugger")
        self.__api.detach()
        self.close_connection(False)

    def __set_features(self):
        """Evaluate vim dictionary of features and pass to debugger.

        Errors are caught if the debugger doesn't like the feature name or
        value. This doesn't break the loop, so multiple features can be set
        even in the case of an error."""
        features = vim.eval('g:vdebug_features')
        for name, value in features.iteritems():
            try:
                self.__api.feature_set(name, value)
            except vdebug.dbgp.DBGPError as e:
                error_str = "Failed to set feature %s: %s" %(name,str(e.args[0]))
                self.__ui.error(error_str)

    def __initialize_breakpoints(self):
        self.__breakpoints.update_lines(self.__ui.get_breakpoint_sign_positions())
        self.__breakpoints.link_api(self.__api)

    def __collect_context_names(self):
        cn_res = self.__api.context_names()
        self.context_names = cn_res.names()
        vdebug.log.Log("Available context names: %s" %\
                str(self.context_names), vdebug.log.Logger.DEBUG)
