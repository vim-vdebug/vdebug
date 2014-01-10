# coding=utf-8

import vdebug.dbgp
import vdebug.log
import vdebug.ui.vimui
import socket
import vim
import vdebug.breakpoint
import vdebug.opts
import vdebug.util
import vdebug.connection

class Runner:
    def __init__(self):
        self.session = None
        self.__context_names = {}

    def start(self, session):
        self.session = session
        self.session.start()
        self.ui = self.session.ui()

    def close(self):
        self.session.close()
        self.session = None

    def is_connected(self):
        return self.session and self.session.is_connected()

    def set_connection(self, connection):
        """Open the vdebug.dbgp API with connection.

        Uses existing connection if possible.
        """
        if self.is_connected():
            vdebug.log.Log("Cannot open a new connection \
                while one already exists",\
                vdebug.log.Logger.ERROR)
            return
        else:
            self.session.set_api(vdebug.dbgp.Api(connection))

    def run(self):
        """Tell the debugger to run.

        It will run until the end of the execution or until a
        breakpoint is reached."""
        self.session.dispatch_event("run")

    def step_over(self):
        """Step over to the next statement."""
        self.session.dispatch_event("step_over")

    def step_into(self):
        """Step into the next statement."""
        self.session.dispatch_event("step_over")

    def step_out(self):
        """Step out of the current context."""
        self.session.dispatch_event("step_out")

    def remove_breakpoint(self,args):
        """Remove a breakpoint, by ID or "*"."""
        self.session.dispatch_event("remove_breakpoint", args)

    def set_breakpoint(self, args):
        self.session.dispatch_event("set_breakpoint", args)

    def eval(self, code):
        """Evaluate a snippet of code and show the response on the watch window.
        """
        self.session.dispatch_event("eval", code)

    def run_to_cursor(self):
        """Tell the debugger to run to the current cursor position.

        This fails if the current window is not the source window.
        """
        self.session.dispatch_event("run_to_cursor")

    def toggle_breakpoint_window(self):
        """Open or close the breakpoint window.

        The window appears as a horizontal split below the
        currently selected window."""
        if self.ui.breakpointwin.is_open:
            self.ui.breakpointwin.destroy()
        else:
            self.ui.breakpointwin.create()

