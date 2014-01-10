# coding=utf-8
import vdebug.log
import vdebug.opts
import vim
import re

class Dispatcher:
    def visual_eval(self, session):
        if session.is_connected():
            event = VisualEvalEvent(session)
            return event.dispatch()

    def eval_under_cursor(self, session):
        if session.is_connected():
            event = CursorEvalEvent(session)
            return event.dispatch()

    def by_position(self, session):
        if session.is_connected():
            event = self._get_event_by_position(session)
            if event is not None:
                return event.dispatch()
            else:
                vdebug.log.Log("No executable event found at current cursor position",\
                        vdebug.log.Logger.DEBUG)
                return False

    def _get_event_by_position(self, session):
        buf_name = vim.current.buffer.name
        p = re.compile('.*[\\\/]([^\\\/]+)')
        m = p.match(buf_name)
        if m is None:
            return None

        window_name = m.group(1)
        if window_name == session.ui().watchwin.name:
            lineno = vim.current.window.cursor[0]
            vdebug.log.Log("User action in watch window, line %s" % lineno,
                            vdebug.log.Logger.DEBUG)
            line = session.ui().watchwin.buffer[lineno-1].strip()
            if lineno == 1:
                return WatchWindowContextChangeEvent(session)
            elif line.startswith(vdebug.opts.Options.get('marker_closed_tree')):
                return WatchWindowPropertyGetEvent(session)
            elif line.startswith(vdebug.opts.Options.get('marker_open_tree')):
                return WatchWindowHideEvent(session)
        elif window_name == session.ui().stackwin.name:
            return StackWindowLineSelectEvent(session)

class Event:
    def __init__(self, session):
        self._session = session

    def dispatch(self):
        pass

class VisualEvalEvent(Event):
    """Evaluate a block of code given by visual selection in Vim.
    """
    def dispatch(self):
        selection = vim.eval("vdebug:get_visual_selection()")
        self._session.dispatch_event("eval", selection)
        return True

class CursorEvalEvent(Event):
    """Evaluate the variable currently under the cursor.
    """
    char_regex = {
        "default" : "a-zA-Z0-9_.\[\]'\"",
        "ruby" : "$@a-zA-Z0-9_.\[\]'\"",
        "perl" : "$a-zA-Z0-9_{}'\"",
        "php" : "$@%a-zA-Z0-9_\[\]'\"\->"
    }

    var_regex = {
        "default" : "^[a-zA-Z_]",
        "ruby" : "^[$@a-zA-Z_]",
        "php" : "^[\$A-Z]",
        "perl" : "^[$@%]"
    }

    def dispatch(self):
        lineno = vim.current.window.cursor[0]
        colno = vim.current.window.cursor[1]
        line = vim.current.buffer[lineno-1]
        lang = self._session.api().language
        if lang in self.char_regex:
            reg = self.char_regex[lang]
        else:
            reg = self.char_regex['default']

        p = re.compile('['+reg+']')
        var = ""
        linelen = len(line)

        for i in range(colno,linelen):
            char = line[i]
            if p.match(char):
                var += char
            else:
                break

        if colno > 0:
            for i in range(colno-1,-1,-1):
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
            self._session.ui().error("Cannot find a valid variable under the cursor")
            return False

        if len(var):
            self._session.dispatch_event("eval", var)
            return True
        else:
            self._session.ui().error("Cannot find a valid variable under the cursor")
            return False

class StackWindowLineSelectEvent(Event):
    """Move the the currently selected file and line in the stack window
    """
    def dispatch(self):
        lineno = vim.current.window.cursor[0]

        vdebug.log.Log("User action in stack window, line %s" % lineno,\
                vdebug.log.Logger.DEBUG)
        line = self._session.ui().stackwin.buffer[lineno-1]
        if line.find(" @ ") == -1:
            return False
        filename_pos = line.find(" @ ") + 3
        file_and_line = line[filename_pos:]
        line_pos = file_and_line.rfind(":")
        file = vdebug.util.LocalFilePath(file_and_line[:line_pos])
        lineno = file_and_line[line_pos+1:]
        self._session.ui().sourcewin.set_file(file)
        self._session.ui().sourcewin.set_line(lineno)

class WatchWindowPropertyGetEvent(Event):
    """Open a tree node in the watch window.

    This retrieves the child nodes and displays them underneath.
    """
    def dispatch(self):
        lineno = vim.current.window.cursor[0]
        line = vim.current.buffer[lineno-1]
        pointer_index = line.find(vdebug.opts.Options.get('marker_closed_tree'))
        step = len(vdebug.opts.Options.get('marker_closed_tree')) + 1

        eq_index = line.find('=')
        if eq_index == -1:
            raise EventError("Cannot read the selected property")

        name = line[pointer_index+step:eq_index-1]
        context_res = self._session.api().property_get(name)
        rend = vdebug.ui.vimui.ContextGetResponseRenderer(context_res)
        output = rend.render(pointer_index - 1)
        self._session.ui().watchwin.delete(lineno,lineno+1)
        self._session.ui().watchwin.insert(output.rstrip(),lineno-1,True)

class WatchWindowHideEvent(Event):
    """Close a tree node in the watch window.
    """
    def dispatch(self):
        lineno = vim.current.window.cursor[0]
        line = vim.current.buffer[lineno-1]
        pointer_index = line.find(vdebug.opts.Options.get('marker_open_tree'))

        buf_len = len(vim.current.buffer)
        end_lineno = buf_len - 1
        for i in range(lineno,end_lineno):
            buf_line = vim.current.buffer[i]
            char = buf_line[pointer_index]
            if char != " ":
                end_lineno = i - 1
                break
        self._session.ui().watchwin.delete(lineno, end_lineno+1)
        if vdebug.opts.Options.get('watch_window_style') == 'expanded':
            append = "\n" + "".rjust(pointer_index) + "|"
        else:
            append = ""
        self._session.ui().watchwin.insert(line.replace(\
                    vdebug.opts.Options.get('marker_open_tree'),\
                    vdebug.opts.Options.get('marker_closed_tree'),1) + \
                append,lineno-1,True)

class WatchWindowContextChangeEvent(Event):
    """Event used to trigger a watch window context change.

    The word under the VIM cursor is retrieved, and context_get called with the
    new context name.
    """

    def dispatch(self):
        column = vim.current.window.cursor[1]
        line = vim.current.buffer[0]

        vdebug.log.Log("Finding context name at column %s" % column,\
                vdebug.log.Logger.DEBUG)

        tab_end_pos = self.__get_word_end(line,column)
        tab_start_pos = self.__get_word_start(line,column)

        if tab_end_pos == -1 or \
                tab_start_pos == -1:
            raise EventError("Failed to find context name under cursor")

        context_name = line[tab_start_pos:tab_end_pos]
        vdebug.log.Log("Context name: %s" % context_name,\
                vdebug.log.Logger.DEBUG)
        if context_name[0] == '*':
            self._session.ui().say("This context is already showing")
            return False

        context_id = self.__determine_context_id(\
                self._session.context_names, context_name)

        if context_id == -1:
            raise EventError("Could not resolve context name")
            return False
        else:
            self._session.get_context(context_id)
            return True

    def __get_word_end(self,line,column):
        tab_end_pos = -1
        line_len = len(line)
        i = column
        while i < line_len:
            if line[i] == ']':
                tab_end_pos = i-1
                break
            i += 1
        return tab_end_pos

    def __get_word_start(self, line, column):
        tab_start_pos = -1
        j = column
        while j >= 0:
            if line[j] == '[':
                tab_start_pos = j+2
                break
            j -= 1
        return tab_start_pos

    def __determine_context_id(self, context_names, context_name):
        found_id = -1
        for id in context_names.keys():
            name = context_names[id]
            vdebug.log.Log("%s, %s" % (name, context_name))
            if name == context_name:
                found_id = id
                break
        return found_id

class EventError(Exception):
    pass

class RunEvent(Event):
    def dispatch(self):
        vdebug.log.Log("Running")
        self._session.ui().statuswin.set_status("running")
        res = self._session.api().run()
        self._session.refresh(res)

class StepOverEvent(Event):
    def dispatch(self):
        vdebug.log.Log("Stepping over")
        self._session.ui().statuswin.set_status("running")
        res = self._session.api().step_over()
        self._session.refresh(res)

class StepIntoEvent(Event):
    def dispatch(self):
        vdebug.log.Log("Stepping into statement")
        self._session.ui().statuswin.set_status("running")
        res = self._session.api().step_into()
        self._session.refresh(res)

class StepOutEvent(Event):
    def dispatch(self):
        vdebug.log.Log("Stepping out of statement")
        self._session.ui().statuswin.set_status("running")
        res = self._session.api().step_out()
        self._session.refresh(res)

class RunToCursorEvent(Event):
    def dispatch(self):
        row = self._session.ui().get_current_row()
        file = self._session.ui().get_current_file()
        if file != self._session.ui().sourcewin.get_file():
            self._session.ui().error("Run to cursor only works in the source window!")
            return
        vdebug.log.Log("Running to position: line %s of %s" %(row, file))
        bp = vdebug.breakpoint.TemporaryLineBreakpoint(self._session.ui(), file, row)
        self._session.api().breakpoint_set(bp.get_cmd())
        self._session.dispatch_event("run")

class EvalEvent(Event):
    def dispatch(self, code):
        try:
            vdebug.log.Log("Evaluating code: %s" % code)
            context_res = self._session.api().eval(code)
            rend = vdebug.ui.vimui.ContextGetResponseRenderer(\
                    context_res,\
                    "Eval of: '%s'" % context_res.get_code())
            self._session.ui().watchwin.clean()
            self._session.ui().watchwin.accept_renderer(rend)
        except vdebug.dbgp.EvalError:
            self._session.ui().error("Failed to evaluate invalid code, '%s'" % code)

class SetBreakpointEvent(Event):
    def dispatch(self, args):
        bp = vdebug.breakpoint.Breakpoint.parse(self._session.ui(), args)
        if bp.type == "line":
            id = self._session.breakpoints().find_breakpoint(\
                    bp.get_file(),\
                    bp.get_line())
            if id is not None:
                self._session.breakpoints().remove_breakpoint_by_id(id)
                return
        self._session.breakpoints().add_breakpoint(bp)

class RemoveBreakpointEvent(Event):
    def dispatch(self, args):
        if args is None:
            args = ""
        args = args.strip()
        if len(args) == 0:
            self._session.ui().error("ID or '*' required to remove a breakpoint: run "+\
                    "':breakpointWindow' to see breakpoints and their IDs")
            return

        if args == '*':
            self._session.breakpoints().clear_breakpoints()
        else:
            arg_parts = args.split(" ")
            for id in arg_parts:
                self._session.breakpoints().remove_breakpoint_by_id(id)

