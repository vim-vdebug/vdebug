# coding=utf-8
import re

import vim

from . import breakpoint
from . import dbgp
from . import error
from . import log
from . import opts
from . import util
from .ui import vimui


class Event:
    def __init__(self, session_handler):
        log.Log("** %s" % self.__class__.__name__,
                log.Logger.DEBUG)
        self.session_handler = session_handler
        self.session = session_handler.session()
        self.ui = session_handler.ui()
        if self.session:
            self.api = self.session.api()
        else:
            self.api = None

    def run(self, *args):
        pass

    def dispatch(self, name, *args):
        Dispatcher(self.session_handler).dispatch_event(name, *args)


class VisualEvalEvent(Event):
    """Evaluate a block of code given by visual selection in Vim.
    """
    def run(self):
        selection = vim.eval("Vdebug_get_visual_selection()")
        self.dispatch("eval", selection)
        return True


class CursorEvalEvent(Event):
    """Evaluate the variable currently under the cursor.
    """
    char_regex = {
        "default": "a-zA-Z0-9_.\[\]'\"",
        "ruby": "$@a-zA-Z0-9_.\[\]'\"",
        "perl": "$a-zA-Z0-9_{}'\"",
        "php": "$@%a-zA-Z0-9_\[\]'\"\->"
    }

    var_regex = {
        "default": "^[a-zA-Z_]",
        "ruby": "^[$@a-zA-Z_]",
        "php": "^[\$A-Z]",
        "perl": "^[$@%]"
    }

    def run(self):
        lineno = vim.current.window.cursor[0]
        colno = vim.current.window.cursor[1]
        line = vim.current.buffer[lineno-1]
        lang = self.api.language
        if lang in self.char_regex:
            reg = self.char_regex[lang]
        else:
            reg = self.char_regex['default']

        p = re.compile('['+reg+']')
        var = ""
        linelen = len(line)

        for i in range(colno, linelen):
            char = line[i]
            if p.match(char):
                var += char
            else:
                break

        if colno > 0:
            for i in range(colno-1, -1, -1):
                char = line[i]
                if p.match(char):
                    var = char + var
                else:
                    break

        if lang in self.var_regex:
            reg = self.var_regex[lang]
        else:
            reg = self.var_regex["default"]

        f = re.compile(reg)
        if f.match(var) is None:
            self.ui.error("Cannot find a valid variable under the cursor")
            return False

        if var:
            self.dispatch("eval", var)
            return True
        self.ui.error("Cannot find a valid variable under the cursor")
        return False


class StackWindowLineSelectEvent(Event):

    """Move the the currently selected file and line in the stack window
    """

    def run(self):
        lineno = vim.current.window.cursor[0]

        log.Log("User action in stack window, line %s" % lineno,
                log.Logger.DEBUG)
        line = self.ui.windows.stack().line_at(lineno - 1)
        if line.find(" @ ") == -1:
            return False

        stack_number_startpos = line.find("[") + 1
        stack_number_endpos = line[stack_number_startpos:].rfind("]") + 1
        stack_number = line[stack_number_startpos:stack_number_endpos]

        filename_pos = line.find(" @ ") + 3
        file_and_line = line[filename_pos:]
        line_pos = file_and_line.rfind(":")
        file = util.LocalFilePath(file_and_line[:line_pos])
        lineno = file_and_line[line_pos+1:]
        self.ui.sourcewin.set_file(file)
        self.ui.sourcewin.set_line(lineno)

        self.dispatch("change_stack", stack_number)


class WatchWindowPropertyGetEvent(Event):

    """Open a tree node in the watch window.

    This retrieves the child nodes and displays them underneath.
    """

    def run(self):
        lineno = vim.current.window.cursor[0]
        line = vim.current.buffer[lineno-1]
        pointer_index = line.find(opts.Options.get('marker_closed_tree'))
        step = len(opts.Options.get('marker_closed_tree')) + 1

        eq_index = line.find('=')
        if eq_index == -1:
            raise error.EventError("Cannot read the selected property")

        name = line[pointer_index+step:eq_index-1]
        context_res = self.api.property_get(name)
        rend = vimui.ContextGetResponseRenderer(context_res)
        output = rend.render(pointer_index - 1)
        if opts.Options.get('watch_window_style') == 'expanded':
            self.ui.windows.watch().delete(lineno, lineno+1)
        self.ui.windows.watch().insert(output.rstrip(), lineno-1, True)


class WatchWindowHideEvent(Event):

    """Close a tree node in the watch window.
    """

    def run(self):
        lineno = vim.current.window.cursor[0]
        line = vim.current.buffer[lineno-1]
        pointer_index = line.find(opts.Options.get('marker_open_tree'))

        buf_len = len(vim.current.buffer)
        end_lineno = buf_len - 1
        for i in range(lineno, end_lineno):
            buf_line = vim.current.buffer[i]

            # If the value of the variable contains a new line and the new line
            # is shorter than the variables tree level, skip it, to avoid an
            # IndexError
            if pointer_index >= len(buf_line):
                continue

            char = buf_line[pointer_index]
            if char != " ":
                end_lineno = i - 1
                break
        self.ui.windows.watch().delete(lineno, end_lineno+1)
        if opts.Options.get('watch_window_style') == 'expanded':
            append = "\n" + "".rjust(pointer_index) + "|"
        else:
            append = ""
        self.ui.windows.watch().insert(line.replace(
            opts.Options.get('marker_open_tree'),
            opts.Options.get('marker_closed_tree'), 1)+append, lineno-1, True)


class WatchWindowContextChangeEvent(Event):

    """Event used to trigger a watch window context change.

    The word under the VIM cursor is retrieved, and context_get called with the
    new context name.
    """

    def run(self):
        column = vim.current.window.cursor[1]
        line = vim.current.buffer[0]

        log.Log("Finding context name at column %s" % column, log.Logger.DEBUG)

        tab_end_pos = self.__get_word_end(line, column)
        tab_start_pos = self.__get_word_start(line, column)

        if tab_end_pos == -1 or tab_start_pos == -1:
            raise error.EventError("Failed to find context name under cursor")

        context_name = line[tab_start_pos:tab_end_pos]
        log.Log("Context name: %s" % context_name, log.Logger.DEBUG)
        if context_name[0] == '*':
            self.ui.say("This context is already showing")
            return False

        context_id = self.__determine_context_id(self.session.context_names,
                                                 context_name)

        if context_id == -1:
            raise error.EventError("Could not resolve context name")

        self.ui.selected_context = context_id

        if self.ui.selected_stack is None:
            self.dispatch("get_context", context_id)
        else:
            self.dispatch("change_stack", self.ui.selected_stack)
        return True

    @staticmethod
    def __get_word_end(line, column):
        tab_end_pos = -1
        line_len = len(line)
        i = column
        while i < line_len:
            if line[i] == ']':
                tab_end_pos = i-1
                break
            i += 1
        return tab_end_pos

    @staticmethod
    def __get_word_start(line, column):
        tab_start_pos = -1
        j = column
        while j >= 0:
            if line[j] == '[':
                tab_start_pos = j+2
                break
            j -= 1
        return tab_start_pos

    @staticmethod
    def __determine_context_id(context_names, context_name):
        found_id = -1
        for id in context_names.keys():
            name = context_names[id]
            log.Log("%s, %s" % (name, context_name))
            if name == context_name:
                found_id = id
                break
        return found_id


class RefreshEvent(Event):

    def run(self, status):

        status_str = str(status)

        if not status_str:
            return

        if status_str == "interactive":
            self.ui.error("Debugger engine says it is in interactive mode,"
                          "which is not supported: closing connection")
            log.Log("closing connection because of interactive mode")
            self.session.close_connection()
        elif status_str in ("stopping", "stopped"):
            self.ui.set_status("stopped")
            self.ui.say("Debugging session has ended")
            log.Log("closing connection because status is stopped")
            self.session.close_connection(False)
            if opts.Options.get('continuous_mode', int) != 0:
                self.dispatch("listen")
        else:
            log.Log("Getting stack information")
            self.ui.set_status(status)
            stack_res = self.__update_stack()
            stack = stack_res.get_stack()

            self.session.cur_file = util.RemoteFilePath(
                stack[0].get('filename'))
            self.session.cur_lineno = stack[0].get('lineno')

            log.Log("Moving to current position in source window")
            self.ui.set_source_position(self.session.cur_file,
                                        self.session.cur_lineno)

            self.dispatch("get_context", 0)

    def __update_stack(self):
        """Update the stack window with the current stack info.
        """
        res = self.api.stack_get()
        renderer = vimui.StackGetResponseRenderer(res)
        self.ui.windows.stack().accept_renderer(renderer)
        return res


class RunEvent(Event):

    def run(self):
        if self.session.is_connected():
            log.Log("Running")
            self.ui.set_status("running")
            res = self.api.run()
            self.dispatch("refresh", res)
        else:
            self.dispatch("listen")


class ListenEvent(Event):

    def run(self):
        self.session_handler.listen()


class StepOverEvent(Event):

    def run(self):
        if not self.session or not self.session.is_connected():
            self.ui.say("Step over is only possible when "
                          "Vdebug is running")
            return False

        log.Log("Stepping over")
        self.ui.set_status("running")
        res = self.api.step_over()
        self.dispatch("refresh", res)


class StepIntoEvent(Event):

    def run(self):
        if not self.session or not self.session.is_connected():
            self.ui.say("Step in is only possible when "
                          "Vdebug is running")
            return False

        log.Log("Stepping into statement")
        self.ui.set_status("running")
        res = self.api.step_into()
        self.dispatch("refresh", res)


class StepOutEvent(Event):

    def run(self):
        if not self.session or not self.session.is_connected():
            self.ui.say("Step out is only possible when "
                          "Vdebug is running")
            return False

        log.Log("Stepping out of statement")
        self.ui.set_status("running")
        res = self.api.step_out()
        self.dispatch("refresh", res)


class RunToCursorEvent(Event):

    def run(self):
        if not self.session or not self.session.is_connected():
            self.ui.say("Run to cursor is only possible when "
                          "Vdebug is running")
            return False

        row = self.ui.get_current_row()
        file = self.ui.get_current_file()
        if file != self.ui.sourcewin.get_file():
            self.ui.error("Run to cursor only works in the source window!")
            return
        log.Log("Running to position: line %s of %s" % (row, file))
        bp = breakpoint.TemporaryLineBreakpoint(self.ui, file, row)
        self.api.breakpoint_set(bp.get_cmd())
        self.dispatch("run")


class EvalEvent(Event):

    def run(self, code):
        try:
            log.Log("Evaluating code: %s" % code)

            context_res = self.api.eval(code)
            rend = vimui.ContextGetResponseRenderer(
                context_res, "Eval of: '%s'" % context_res.get_code())

            self.ui.windows.watch().accept_renderer(rend)
        except dbgp.EvalError:
            self.ui.error("Failed to evaluate invalid code, '%s'" % code)


class SetEvalExpressionEvent(Event):

    def run(self, persist_expression, code):
        if not self.session or not self.session.is_connected():
            self.ui.error("Evaluating an expression is only possible when "
                          "Vdebug is running")
            return

        log.Log("Evaluating code: %s" % code)

        if code:
            if persist_expression:
                self.ui.windows.watch().set_eval_expression(code)
            self.dispatch("eval", code)
        else:
            self.ui.windows.watch().clear_eval_expression()
            self.dispatch("get_context", 0)


class SetBreakpointEvent(Event):

    def run(self, args):
        # Adding a special case to try a breakpoint on an empty line since the Breakpoint parser throws an error for
        # that scenario
        if not args:
            line = self.ui.get_current_line()
            if not line.strip():
                file = self.ui.get_current_file()
                row = self.ui.get_current_row()

                id = self.session_handler.breakpoints().find_breakpoint(file, row)
                if id is not None:
                    self.session_handler.breakpoints().remove_breakpoint_by_id(id)
                    return

        bp = breakpoint.Breakpoint.parse(self.ui, args)
        if bp.type == "line":
            id = self.session_handler.breakpoints().find_breakpoint(
                bp.get_file(), bp.get_line())
            if id is not None:
                self.session_handler.breakpoints().remove_breakpoint_by_id(id)
                return
        self.session_handler.breakpoints().add_breakpoint(bp)


class BreakpointStatusEvent(Event):
    def parseArgs(self, args):
        if args is None:
            args = ""
        args = args.strip()

        arg_parts = args.split(' ')
        first_param = arg_parts.pop(0)
        if first_param == "":
            return { "id": None, "action": None }

        if first_param in ("toggle", "enable", "disable"):
            return { "id": None, "action": first_param }

        if len(arg_parts) == 0:
            return { "id": first_param , "action": None }

        second_param = arg_parts.pop(0)
        return { "id": first_param, "action": second_param }

    def get_breakpoint(self, id):
        if id is not None:
            return self.session_handler.breakpoints().get_breakpoint_by_id(id)

        """ Line breakpoint """
        try:
            file = self.ui.get_current_file()
            line = self.ui.get_current_row()
            id = self.session_handler.breakpoints().find_breakpoint(file, line)
            if id is None:
                return None

            return self.session_handler.breakpoints().get_breakpoint_by_id(id)
        except error.FilePathError:
            raise error.BreakpointError('No file, cannot set breakpoint')

    def run(self, args):
        parsed_args = self.parseArgs(args)
        id = parsed_args["id"]
        action = parsed_args["action"]
        bp = self.get_breakpoint(id)

        if bp is None:
            print("No breakpoint found")
            return

        if action is None:
            print("enabled" if bp.enabled else "disabled")
            return

        if action == "enable":
            return self.dispatch("enable_breakpoint", str(bp.id))

        if action == "disable":
            return self.dispatch("disable_breakpoint", str(bp.id))

        if action == "toggle":
            return self.dispatch("toggle_breakpoint", str(bp.id))


class CycleBreakpointStatusEvent(BreakpointStatusEvent):

    def run(self, args):
        parsed_args = self.parseArgs(args)
        id = parsed_args["id"]
        bp = self.get_breakpoint(id)

        if bp is None:
            self.dispatch("set_breakpoint", args)
            return

        if bp is not None:
            if bp.enabled:
                self.session_handler.breakpoints().disable_breakpoint_by_id(bp.id)
            else:
                self.session_handler.breakpoints().remove_breakpoint_by_id(bp.id)


class ToggleBreakpointEvent(BreakpointStatusEvent):

    def run(self, args):
        parsed_args = self.parseArgs(args)
        id = parsed_args["id"]
        bp = self.get_breakpoint(id)

        if bp is not None and bp.type == "line":
            self.session_handler.breakpoints().toggle_breakpoint_by_id(bp.id)


class EnableBreakpointEvent(BreakpointStatusEvent):

    def run(self, args):
        parsed_args = self.parseArgs(args)
        id = parsed_args["id"]
        bp = self.get_breakpoint(id)

        if bp is not None and bp.type == "line":
            self.session_handler.breakpoints().enable_breakpoint_by_id(id)


class DisableBreakpointEvent(BreakpointStatusEvent):

    def run(self, args):
        parsed_args = self.parseArgs(args)
        id = parsed_args["id"]
        bp = self.get_breakpoint(id)

        if bp is not None and bp.type == "line":
            self.session_handler.breakpoints().disable_breakpoint_by_id(id)


class RemoveBreakpointEvent(Event):

    def run(self, args):
        if args is None:
            args = ""
        args = args.strip()
        if not args:
            self.ui.error("ID or '*' required to remove a breakpoint: run "
                          "':BreakpointWindow' to see breakpoints and their "
                          "IDs")
            return

        if args == '*':
            self.session_handler.breakpoints().clear_breakpoints()
        else:
            arg_parts = args.split(" ")
            for id in arg_parts:
                self.session_handler.breakpoints().remove_breakpoint_by_id(id)


class GetContextEvent(Event):

    def run(self, context_id):
        if self.ui.windows.watch().has_persistent_eval():
            self.dispatch("eval",
                          self.ui.windows.watch().get_eval_expression())
        else:
            name = self.session.context_names[context_id]
            log.Log("Getting %s variables" % name)
            context_res = self.api.context_get(context_id)
            rend = vimui.ContextGetResponseRenderer(
                context_res, "%s at %s:%s" % (name, self.ui.sourcewin.file,
                                              self.session.cur_lineno),
                self.session.context_names, context_id)
            self.ui.windows.watch().accept_renderer(rend)
            self.ui.selected_stack = None
            self.ui.selected_context = context_id

        self.dispatch("trace_refresh")


class TraceRefreshEvent(Event):

    def run(self):
        if self.ui.windows.trace().is_tracing():
            trace_expr = self.ui.windows.trace().get_trace_expression()
            log.Log("Tracing expression: %s" % trace_expr)
            try:
                context_res = self.api.eval(trace_expr)
                rend = vimui.ContextGetResponseRenderer(
                    context_res, "Trace of: '%s'" % context_res.get_code())
                self.ui.windows.trace().render(rend)
            except dbgp.EvalError:
                self.ui.windows.trace().render_in_error_case()


class ReloadKeymappingsEvent(Event):

    def run(self):
        if self.session:
            print("Reloaded keymappings")
            self.session.keymapper().reload()


class TraceEvent(Event):

    def run(self, code):
        """Evaluate a snippet of code and show the response on the watch window.
        """
        if not self.session or not self.session.is_connected():
            self.ui.error("Tracing an expression is only possible when Vdebug "
                          "is running")
            return
        if not code:
            self.ui.error("You must supply an expression to trace, with "
                          "`:VdebugTrace expr`")
            return

        log.Log("Setting trace expression: %s" % code)

        if self.ui.windows.trace().is_open:
            self.ui.windows.trace().clean()
        else:
            self.ui.windows.open("DebuggerTrace")

        self.ui.windows.trace().set_trace_expression(code)
        self.dispatch("trace_refresh")


class DetachEvent(Event):

    def run(self):
        self.session.detach()


class ChangeStackEvent(Event):

    def run(self, args):
        if args is None or args == "":
            args = "0"

        res = self.api.stack_get()
        ids = list(map(lambda s: s.get('level'), res.get_stack()))

        if args not in ids:
            print("The selected stack does not exist")
            return

        stack = next(s for s in res.get_stack() if s.get('level') == args)

        context_id = self.ui.selected_context
        name = self.session.context_names[context_id]
        log.Log("Getting %s variables" % name)
        context_res = self.api.context_get(context_id, args)
        rend = vimui.ContextGetResponseRenderer(
            context_res, "%s at %s:%s" % (name, str(util.FilePath(stack.get('filename')).as_local()),
                                          stack.get('lineno')),
            self.session.context_names, context_id)
        self.ui.selected_stack = args
        self.ui.windows.watch().accept_renderer(rend)

        self.dispatch("trace_refresh")

class Dispatcher:
    events = {
        "run": RunEvent,
        "refresh": RefreshEvent,
        "listen": ListenEvent,
        "step_over": StepOverEvent,
        "step_into": StepIntoEvent,
        "step_out": StepOutEvent,
        "run_to_cursor": RunToCursorEvent,
        "eval": EvalEvent,
        "set_eval_expression": SetEvalExpressionEvent,
        "set_breakpoint": SetBreakpointEvent,
        "cycle_breakpoint": CycleBreakpointStatusEvent,
        "toggle_breakpoint": ToggleBreakpointEvent,
        "enable_breakpoint": EnableBreakpointEvent,
        "disable_breakpoint": DisableBreakpointEvent,
        "breakpoint_status": BreakpointStatusEvent,
        "get_context": GetContextEvent,
        "reload_keymappings": ReloadKeymappingsEvent,
        "remove_breakpoint": RemoveBreakpointEvent,
        "trace": TraceEvent,
        "trace_refresh": TraceRefreshEvent,
        "detach": DetachEvent,
        "change_stack": ChangeStackEvent,
    }

    def __init__(self, session_handler):
        self.__session_handler = session_handler
        self.__ex_handler = util.ExceptionHandler(self.__session_handler)

    def dispatch_event(self, name, *args):
        try:
            Dispatcher.events[name](self.__session_handler).run(*args)
        except Exception as e:
            self.__ex_handler.handle(e)

    def visual_eval(self, session):
        if session.is_connected():
            event = VisualEvalEvent(session)
            return event.run()

    @staticmethod
    def eval_under_cursor(session):
        if session.is_connected():
            event = CursorEvalEvent(session)
            return event.run()

    def by_position(self, session):
        if session.is_connected():
            event = self._get_event_by_position(session)
            if event is not None:
                return event.run()
            log.Log("No executable event found at current cursor position",
                    log.Logger.DEBUG)
            return False

    @staticmethod
    def _get_event_by_position(session):
        buf_name = vim.current.buffer.name
        p = re.compile(r'.*[\\/]([^\\/]+)')
        m = p.match(buf_name)
        if m is None:
            return None

        window_name = m.group(1)
        if window_name == session.ui().windows.watch().name:
            lineno = vim.current.window.cursor[0]
            log.Log("User action in watch window, line %s" % lineno,
                    log.Logger.DEBUG)
            line = session.ui().windows.watch().line_at(lineno - 1).strip()
            if lineno == 1:
                return WatchWindowContextChangeEvent(session)
            elif line.startswith(opts.Options.get('marker_closed_tree')):
                return WatchWindowPropertyGetEvent(session)
            elif line.startswith(opts.Options.get('marker_open_tree')):
                return WatchWindowHideEvent(session)
        elif window_name == session.ui().windows.stack().name:
            return StackWindowLineSelectEvent(session)
