import vim

from . import breakpoint
from . import event
from . import opts
from . import session
from . import util
from .ui import vimui


class DebuggerInterface:
    """Provides all methods used to control the debugger."""
    def __init__(self):
        self.breakpoints = breakpoint.Store()
        self.ui = vimui.Ui()

        self.session_handler = session.SessionHandler(self.ui,
                                                      self.breakpoints)
        self.event_dispatcher = event.Dispatcher(self.session_handler)

    def __del__(self):
        self.session_handler.close()
        self.session_handler = None

    def change_stack(self, args=None):
        self.session_handler.dispatch_event("change_stack", args)

    @staticmethod
    def reload_options():
        util.Environment.reload()

    def reload_keymappings(self):
        self.session_handler.dispatch_event("reload_keymappings")

    def status(self):
        return self.session_handler.status()

    def status_for_statusline(self):
        return self.session_handler.status_for_statusline()

    def start_if_ready(self):
        self.session_handler.start_if_ready()

    def listen(self):
        self.session_handler.listen()

    def run(self):
        """Tell the debugger to run, until the next breakpoint or end of script.
        """
        self.session_handler.run()

    def run_to_cursor(self):
        """Run to the current VIM cursor position.
        """
        self.session_handler.dispatch_event("run_to_cursor")

    def step_over(self):
        """Step over to the next statement.
        """
        self.session_handler.dispatch_event("step_over")

    def step_into(self):
        """Step into a statement on the current line.
        """
        self.session_handler.dispatch_event("step_into")

    def step_out(self):
        """Step out of the current statement.
        """
        self.session_handler.dispatch_event("step_out")

    def handle_return_keypress(self):
        """React to a <enter> keypress event.
        """
        return self.event_dispatcher.by_position(self.session_handler)

    def handle_delete_line_keypress(self):
        """React to a <dd> keypress event.
        """
        return self.event_dispatcher.delete_line(self.session_handler)

    def handle_delete_visual_keypress(self):
        """React to a vunmap<d> keypress event.
        """
        return self.event_dispatcher.delete_visual(self.session_handler)

    def handle_double_click(self):
        """React to a mouse double click event.
        """
        return self.event_dispatcher.by_position(self.session_handler)

    def handle_visual_eval(self):
        """React to eval during visual selection.
        """
        return self.event_dispatcher.visual_eval(self.session_handler)

    def handle_eval(self, bang, args):
        """Evaluate a code snippet specified by args.
        """
        return self.session_handler.dispatch_event("set_eval_expression",
                                                   len(bang) > 0, args)

    def handle_trace(self, args=None):
        """Trace a code snippet specified by args.
        """
        return self.session_handler.dispatch_event("trace", args)

    def eval_under_cursor(self):
        """Evaluate the property under the cursor.
        """
        return self.event_dispatcher.eval_under_cursor(self.session_handler)

    def mark_window_as_closed(self, window):
        self.session_handler.ui().mark_window_as_closed(window)

    def toggle_window(self, name):
        self.session_handler.ui().toggle_window(name)

    def toggle_breakpoint_window(self):
        self.session_handler.ui().toggle_window("DebuggerBreakpoints")

    def get_last_error(self):
        return self.session_handler.ui().get_last_error()

    def set_breakpoint(self, args=None):
        """Set a breakpoint, specified by args.
        """
        self.session_handler.dispatch_event("set_breakpoint", args)

    def cycle_breakpoint(self, args=None):
        """Cycle a breakpoint between Enabled, Disabled and Removed
        """
        self.session_handler.dispatch_event("cycle_breakpoint", args)

    def toggle_breakpoint(self, args=None):
        """Toggle a breakpoint, specified by args
        """
        self.session_handler.dispatch_event("toggle_breakpoint", args)

    def enable_breakpoint(self, args=None):
        """Enable a breakpoint, specified by args
        """
        self.session_handler.dispatch_event("enable_breakpoint", args)

    def disable_breakpoint(self, args=None):
        """Disable a breakpoint, specified by args
        """
        self.session_handler.dispatch_event("disable_breakpoint", args)

    def breakpoint_status(self, args=None):
        """Either gets the status of a breakpoint or changes it
        """
        self.session_handler.dispatch_event("breakpoint_status", args)

    def remove_breakpoint(self, args=None):
        """Remove one or more breakpoints, specified by args.
        """
        self.session_handler.dispatch_event("remove_breakpoint", args)

    def jump_breakpoint(self, args=None):
        """Jump to a breakpoint in the source window from the breakpoint window
        """
        self.session_handler.dispatch_event("breakpoint_jump", args)

    def get_context(self):
        """Get all the variables in the default context
        """
        self.session_handler.dispatch_event("get_context", 0)

    def detach(self):
        """Detach the debugger, so the script runs to the end.
        """
        self.session_handler.dispatch_event("detach")

    def close(self):
        """Close the connection, or the UI if already closed.
        """
        self.session_handler.stop()
