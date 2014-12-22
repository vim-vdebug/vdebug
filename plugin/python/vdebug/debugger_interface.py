import vdebug.event
import vdebug.listener
import vdebug.session
import vdebug.util
import vdebug.breakpoint
import vdebug.ui.vimui
import vdebug.opts
import vim

class DebuggerInterface:
    """Provides all methods used to control the debugger."""
    def __init__(self):
        self.breakpoints = vdebug.breakpoint.Store()
        self.ui = vdebug.ui.vimui.Ui()

        self.session_handler = vdebug.session.SessionHandler(self.ui,
                                    self.breakpoints)
        self.event_dispatcher = vdebug.event.Dispatcher(self.session_handler)

    def __del__(self):
        self.session_handler.stop()
        self.session_handler = None

    def reload_options(self):
        vdebug.util.Environment.reload()

    def reload_keymappings(self):
        self.session_handler.dispatch_event("reload_keymappings")

    def status(self):
        return self.session_handler.status()

    def status_for_statusline(self):
        return self.session_handler.status_for_statusline()

    def handle_periodically(self):
        return self.session_handler.periodically()

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

    def handle_opt(self, option, value = None):
        """Set an option, overwriting the existing value.
        """
        if value is None:
            return self.ui.say(vdebug.opts.Options.get(option))
        else:
            self.ui.say("Setting vdebug option '%s' to: %s"\
                                %(option,value))
            vim.command('let g:vdebug_options["%s"] = "%s"' %(option,value))
            return vdebug.opts.Options.overwrite(option,value)

    def handle_return_keypress(self):
        """React to a <enter> keypress event.
        """
        return self.event_dispatcher.by_position(self.session_handler)

    def handle_double_click(self):
        """React to a mouse double click event.
        """
        return self.event_dispatcher.by_position(self.session_handler)

    def handle_visual_eval(self):
        """React to eval during visual selection.
        """
        return self.event_dispatcher.visual_eval(self.session_handler)

    def handle_eval(self,args):
        """Evaluate a code snippet specified by args.
        """
        return self.session_handler.dispatch_event("eval", args)

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

    def set_breakpoint(self,args = None):
        """Set a breakpoint, specified by args.
        """
        self.session_handler.dispatch_event("set_breakpoint", args)

    def remove_breakpoint(self,args = None):
        """Remove one or more breakpoints, specified by args.
        """
        self.session_handler.dispatch_event("remove_breakpoint", args)

    def get_context(self):
        """Get all the variables in the default context
        """
        self.session_handler.dispatch_event("get_context")

    def detach(self):
        """Detach the debugger, so the script runs to the end.
        """
        self.session_handler.dispatch_event("detach")

    def close(self):
        """Close the connection, or the UI if already closed.
        """
        self.session_handler.stop()
