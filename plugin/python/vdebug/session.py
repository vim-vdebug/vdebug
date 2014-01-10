import vdebug.util
import vdebug.opts
import vdebug.log
import vdebug.dbgp
import vim

class ModifiedBufferError(Exception):
    pass

class NoConnectionError(Exception):
    pass

class Session:
    events = {
        "run": vdebug.event.RunEvent,
        "step_over": vdebug.event.StepOverEvent,
        "step_into": vdebug.event.StepIntoEvent,
        "step_out": vdebug.event.StepOutEvent,
        "run_to_cursor": vdebug.event.RunToCursorEvent,
        "eval": vdebug.event.EvalEvent,
        "set_breakpoint": vdebug.event.SetBreakpointEvent,
        "remove_breakpoint": vdebug.event.RemoveBreakpointEvent
    }

    def __init__(self, ui, breakpoints, keymapper):
        self.__ui = ui
        self.__breakpoints = breakpoints
        self.__keymapper = keymapper
        self.__api = None
        self.__ex_handler = vdebug.util.ExceptionHandler(self)

    def ui(self):
        return self.__ui

    def breakpoints(self):
        return self.__breakpoints

    def dispatch_event(self, name, *args):
        try:
            Session.events[name](self).dispatch(*args)
        except Exception, e:
            self.__ex_handler.handle(e)

    def api(self):
        if self.__api:
            return self.__api
        else:
            raise NoConnectionError("No debugger connection")

    def set_api(self, api):
        self.__api = api

    def is_connected(self):
        return self.__api is not None

    def is_open(self):
        return self.__ui.is_open

    def close(self):
        """ Close both the connection and vdebug.ui.
        """
        self.close_connection()
        self.__ui.close()
        self.__keymapper.unmap()

    def refresh(self, status):
        """The main action performed after a deubugger step.

        Updates the status window, current stack, source
        file and line and watch window."""

        if str(status) == "interactive":
            self.__ui.error("Debugger engine says it is in interactive mode,"+\
                    "which is not supported: closing connection")
            self.__breakpoints.unlink_api()
            self.close_connection()
        elif str(status) in ("stopping","stopped"):
            self.__ui.statuswin.set_status("stopped")
            self.__ui.say("Debugging session has ended")
            self.__breakpoints.unlink_api()
            self.close_connection(False)
            if vdebug.opts.Options.get('continuous_mode', int) != 0:
                self.open()
                return
        else:
            vdebug.log.Log("Getting stack information")
            self.__ui.statuswin.set_status(status)
            stack_res = self.__update_stack()
            stack = stack_res.get_stack()

            self.cur_file = vdebug.util.RemoteFilePath(stack[0].get('filename'))
            self.cur_lineno = stack[0].get('lineno')

            vdebug.log.Log("Moving to current position in source window")
            self.__ui.set_source_position(\
                    self.cur_file,\
                    self.cur_lineno)

            self.get_context(0)

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
            self.refresh(status)

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

    def __update_stack(self):
        """Update the stack window with the current stack info.
        """
        self.__ui.stackwin.clean()
        res = self.__api.stack_get()
        renderer = vdebug.ui.vimui.StackGetResponseRenderer(res)
        self.__ui.stackwin.accept_renderer(renderer)
        return res

    def __collect_context_names(self):
        cn_res = self.__api.context_names()
        self.context_names = cn_res.names()
        vdebug.log.Log("Available context names: %s" %\
                str(self.context_names), vdebug.log.Logger.DEBUG)


    def get_context(self, context_id = 0):
        self.__ui.watchwin.clean()
        name = self.context_names[context_id]
        vdebug.log.Log("Getting %s variables" % name)
        context_res = self.__api.context_get(context_id)
        rend = vdebug.ui.vimui.ContextGetResponseRenderer(\
                context_res,\
                "%s at %s:%s" %(name, self.__ui.sourcewin.file,self.cur_lineno),\
                self.context_names,\
                context_id)
        self.__ui.watchwin.accept_renderer(rend)

