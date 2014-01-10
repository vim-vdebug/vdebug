import sys
import socket
import traceback

import vdebug.runner
import vdebug.event
import vdebug.listener
import vdebug.session
import vdebug.util
import vim

class DebuggerInterface:
    """Acts as a facade layer to the debugger client.

    Most methods are just redirected to the Runner class. Most
    exceptions are caught and handled here.
    """
    def __init__(self):
        self.runner = vdebug.runner.Runner()
        self.listener = vdebug.listener.Listener()
        self.event_dispatcher = vdebug.event.Dispatcher()
        self.ui = vdebug.ui.vimui.Ui()
        vdebug.util.Environment.reload()

        self.session = vdebug.session.Session(\
                            self.ui,\
                            vdebug.breakpoint.Store(),\
                            vdebug.util.Keymapper())

    def __del__(self):
        self.session.close()
        self.session = None

    def status(self):
        if self.session.is_connected():
            return "running"
        else:
            return self.listener.status()

    def status_for_statusline(self):
        return "vdebug(%s)" % self.status()

    def start_if_ready(self):
        if not self.session.is_connected() and self.listener.is_ready():
            #self.__new_session()
            return True
        else:
            return False

    def listen(self):
        if self.listener.is_listening():
            print "Already waiting for a connection: none found so far"
        elif self.listener.is_ready():
            print "Found connection, starting debugger"
            self.session.start(self.listener.create_connection())
        else:
            print "Vdebug will wait for a connection in the background"
            self.__reload_environment()
            self.listener.start()

    def run(self):
        """Tell the debugger to run, until the next breakpoint or end of script.
        """
        try:
            if self.session.is_connected():
                self.session.dispatch_event("run")
            else:
                self.listen()
        except Exception as e:
            self.handle_exception(e)

    def run_to_cursor(self):
        """Run to the current VIM cursor position.
        """
        try:
            self.session.dispatch_event("run_to_cursor")
        except Exception as e:
            self.handle_exception(e)

    def step_over(self):
        """Step over to the next statement.
        """
        try:
            self.session.dispatch_event("step_over")
        except Exception as e:
            self.handle_exception(e)

    def step_into(self):
        """Step into a statement on the current line.
        """
        try:
            self.session.dispatch_event("step_into")
        except Exception as e:
            self.handle_exception(e)

    def step_out(self):
        """Step out of the current statement.
        """
        try:
            self.session.dispatch_event("step_out")
        except Exception as e:
            self.handle_exception(e)

    def handle_opt(self,option,value = None):
        """Set an option, overwriting the existing value.
        """
        try:
            if value is None:
                return self.ui.say(vdebug.opts.Options.get(option))
            else:
                self.ui.say("Setting vdebug option '%s' to: %s"\
                                    %(option,value))
                vim.command('let g:vdebug_options["%s"] = "%s"' %(option,value))
                return vdebug.opts.Options.overwrite(option,value)

        except Exception as e:
            self.handle_exception(e)


    def handle_return_keypress(self):
        """React to a <enter> keypress event.
        """
        try:
            return self.event_dispatcher.by_position(self.session)
        except Exception as e:
            self.handle_exception(e)

    def handle_double_click(self):
        """React to a mouse double click event.
        """
        try:
            return self.event_dispatcher.by_position(self.session)
        except Exception as e:
            self.handle_exception(e)

    def handle_visual_eval(self):
        """React to eval during visual selection.
        """
        try:
            return self.event_dispatcher.visual_eval(self.session)
        except Exception as e:
            self.handle_exception(e)

    def handle_eval(self,args):
        """Evaluate a code snippet specified by args.
        """
        try:
            return self.session.dispatch_event("eval", args)
        except Exception as e:
            self.handle_exception(e)

    def eval_under_cursor(self):
        """Evaluate the property under the cursor.
        """
        try:
            return self.event_dispatcher.eval_under_cursor(self.session)
        except Exception as e:
            self.handle_exception(e)

    def toggle_breakpoint_window(self):
        """Open or close the breakpoint window.
        """
        try:
            return self.runner.toggle_breakpoint_window()
        except Exception as e:
            self.handle_exception(e)

    def set_breakpoint(self,args = None):
        """Set a breakpoint, specified by args.
        """
        try:
            self.session.dispatch_event("set_breakpoint", args)
        except Exception as e:
            self.handle_exception(e)

    def remove_breakpoint(self,args = None):
        """Remove one or more breakpoints, specified by args.
        """
        try:
            self.session.dispatch_event("remove_breakpoint", args)
        except Exception as e:
            self.handle_exception(e)

    def get_context(self):
        """Get all the variables in the default context
        """
        try:
            self.session.get_context()
        except Exception as e:
            self.handle_exception(e)

    def detach(self):
        """Detach the debugger, so the script runs to the end.
        """
        try:
            self.session.detach()
        except Exception as e:
            self.handle_exception(e)

    def close(self):
        """Close the connection, or the UI if already closed.
        """
        if self.session.is_connected():
            self.session.close_connection()
        elif self.session.is_open():
            self.session.close()
        else:
            self.listener.stop()

    """ Exception handlers """

    def handle_timeout(self):
        """Handle a timeout, which is pretty normal. 
        """
        self.session.close()
        self.ui.say("No connection was made")

    def handle_interrupt(self):
        """Handle a user interrupt, which is pretty normal. 
        """
        self.session.close()
        self.ui.say("Connection cancelled")

    def handle_socket_end(self):
        """Handle a socket closing, which is pretty normal.
        """
        self.ui.say("Connection to the debugger has been closed")
        self.session.close_connection()

    def handle_vim_error(self,e):
        """Handle a VIM error.

        This should NOT occur under normal circumstances.
        """
        self.ui.error("A Vim error occured: %s\n%s"\
                        % (str(e), traceback.format_exc()))

    def handle_readable_error(self,e):
        """Simply print an error, since it is human readable enough.
        """
        self.ui.error(str(e))

    def handle_dbgp_error(self,e):
        """Simply print an error, since it is human readable enough.
        """
        self.ui.error(str(e.args[0]))

    def handle_general_exception(self):
        """Handle an unknown error of any kind.
        """
        self.ui.error("An error occured: %s\n%s"\
                        % (str(sys.exc_info()[0]), traceback.format_exc()))

    def handle_exception(self,e):
        """Switch on the exception type to work out how to handle it.
        """
        if isinstance(e,vdebug.dbgp.TimeoutError):
            self.handle_timeout()
        elif isinstance(e,vdebug.util.UserInterrupt):
            try:
                self.handle_interrupt()
            except:
                pass
        elif isinstance(e,vdebug.event.EventError):
            self.handle_readable_error(e)
        elif isinstance(e,vdebug.breakpoint.BreakpointError):
            self.handle_readable_error(e)
        elif isinstance(e,vdebug.log.LogError):
            self.handle_readable_error(e)
        elif isinstance(e,vdebug.dbgp.DBGPError):
            self.handle_dbgp_error(e)
        elif isinstance(e,(EOFError,socket.error)):
            self.handle_socket_end()
        elif isinstance(e,KeyboardInterrupt):
            print "Keyboard interrupt - debugging session cancelled"
            try:
                self.session.close()
            except:
                pass
        else:
            self.handle_general_exception()
        """
        elif isinstance(e,vim.error):
            self.handle_vim_error(e)
        """

    def __reload_environment(self):
        vdebug.util.Environment.reload()


    def __new_session(self):
        self.session = vdebug.session.Session(\
                            self.listener.create_connection(),\
                            self.ui)
