import base64

from . import error
from . import log


class Store:

    def __init__(self):
        self.breakpoints = {}
        self.api = None

    def link_api(self, api):
        self.api = api
        num_bps = len(self.breakpoints)
        if num_bps > 0:
            log.Log("Registering %i breakpoints with the debugger" % num_bps)
        for bp in self.breakpoints.values():
            res = self.api.breakpoint_set(bp.get_cmd())
            bp.set_debugger_id(res.get_id())

    # Update line-based breakpoints with a dict of IDs and lines
    def update_lines(self, lines):
        for id, line in lines.items():
            try:
                self.breakpoints[id].set_line(line)
                log.Log("Updated line number of breakpoint %s to %s" % (id,
                                                                        line))
            except ValueError:
                pass
                # No method set_line, not a line breakpoint

    def unlink_api(self):
        self.api = None

    def add_breakpoint(self, breakpoint):
        log.Log("Adding " + str(breakpoint))
        self.breakpoints[str(breakpoint.get_id())] = breakpoint
        breakpoint.on_add()
        if self.api is not None:
            res = self.api.breakpoint_set(breakpoint.get_cmd())
            breakpoint.set_debugger_id(res.get_id())

    def toggle_breakpoint_by_id(self, id):
        id = str(id)
        if id not in self.breakpoints:
            raise error.BreakpointError("No breakpoint matching ID %s" % id)
        if self.breakpoints[id].enabled:
            self.disable_breakpoint_by_id(id)
        else:
            self.enable_breakpoint_by_id(id)

    def enable_breakpoint_by_id(self, id):
        id = str(id)
        if id not in self.breakpoints:
            raise error.BreakpointError("No breakpoint matching ID %s" % id)
        dbg_id = self.breakpoints[id].get_debugger_id()
        if dbg_id is not None:
            self.api.breakpoint_enable(dbg_id)
        self.breakpoints[id].on_enable()

    def disable_breakpoint_by_id(self, id):
        id = str(id)
        if id not in self.breakpoints:
            raise error.BreakpointError("No breakpoint matching ID %s" % id)
        dbg_id = self.breakpoints[id].get_debugger_id()
        if dbg_id is not None:
            self.api.breakpoint_disable(dbg_id)
        self.breakpoints[id].on_disable()

    def remove_breakpoint(self, breakpoint):
        self.remove_breakpoint_by_id(breakpoint.get_id())

    def remove_breakpoint_by_id(self, id):
        id = str(id)
        if id not in self.breakpoints:
            raise error.BreakpointError("No breakpoint matching ID %s" % id)
        log.Log("Removing breakpoint id %s" % id)
        if self.api is not None:
            dbg_id = self.breakpoints[id].get_debugger_id()
            if dbg_id is not None:
                self.api.breakpoint_remove(dbg_id)
        self.breakpoints[id].on_remove()
        del self.breakpoints[id]

    def clear_breakpoints(self):
        # We need to copy the keys to a new list, otherwise the for loop
        # complains when items are removed.
        for id in list(self.breakpoints.keys()):
            self.remove_breakpoint_by_id(id)
        self.breakpoints = {}

    def get_breakpoint_by_id(self, id):
        id = str(id)
        if id not in list(self.breakpoints.keys()):
            return None

        return self.breakpoints[id]

    def find_breakpoint(self, file, line):
        found = None
        for bp in self.breakpoints.values():
            if bp.type == "line":
                if bp.get_file() == file and\
                        bp.get_line() == line:
                    found = bp.get_id()
                    break
        return found


class Breakpoint:
    """ Abstract factory for creating a breakpoint object.

    Use the class method parse to create a concrete subclass
    of a specific type.
    """
    type = None
    id = 11000
    dbg_id = None

    def __init__(self, ui):
        self.id = Breakpoint.id
        Breakpoint.id += 1
        self.ui = ui
        self.enabled = True

    def get_id(self):
        return self.id

    def set_debugger_id(self, dbg_id):
        self.dbg_id = dbg_id

    def get_debugger_id(self):
        return self.dbg_id

    def on_add(self):
        self.ui.register_breakpoint(self)

    def on_enable(self):
        self.enabled = True
        self.ui.enable_breakpoint(self)

    def on_disable(self):
        self.enabled = False
        self.ui.disable_breakpoint(self)

    def on_remove(self):
        self.ui.remove_breakpoint(self)

    @staticmethod
    def parse(ui, args):
        if args is None:
            args = ""
        args = args.strip()
        if not args:
            """ Line breakpoint """
            row = ui.get_current_row()
            try:
                file = ui.get_current_file()
                line = ui.get_current_line()
            except error.FilePathError:
                raise error.BreakpointError('No file, cannot set breakpoint')
            if not line.strip():
                raise error.BreakpointError(
                    'Cannot set a breakpoint on an empty line')
            return LineBreakpoint(ui, file, row)
        arg_parts = args.split(' ')
        type = arg_parts.pop(0)
        type.lower()
        if type == 'conditional':
            row = ui.get_current_row()
            file = ui.get_current_file()
            if not arg_parts:
                raise error.BreakpointError(
                    "Conditional breakpoints require a condition to be "
                    "specified")
            cond = " ".join(arg_parts)
            return ConditionalBreakpoint(ui, file, row, cond)
        elif type == 'watch':
            if not arg_parts:
                raise error.BreakpointError(
                    "Watch breakpoints require a condition to be specified")
            expr = " ".join(arg_parts)
            log.Log("Expression: %s" % expr)
            return WatchBreakpoint(ui, expr)
        elif type == 'exception':
            if not arg_parts:
                raise error.BreakpointError(
                    "Exception breakpoints require an exception name to be "
                    "specified")
            return ExceptionBreakpoint(ui, arg_parts[0])
        elif type == 'return':
            l = len(arg_parts)
            if l == 0:
                raise error.BreakpointError(
                    "Return breakpoints require a function name to be "
                    "specified")
            return ReturnBreakpoint(ui, arg_parts[0])
        elif type == 'call':
            l = len(arg_parts)
            if l == 0:
                raise error.BreakpointError(
                    "Call breakpoints require a function name to be specified")
            return CallBreakpoint(ui, arg_parts[0])
        raise error.BreakpointError(
            "Unknown breakpoint type, please choose one of: conditional, "
            "exception, call or return")

    def get_cmd(self):
        pass

    def __str__(self):
        return "%s breakpoint, id %i" % (self.type, self.id)


class LineBreakpoint(Breakpoint):
    type = "line"

    def __init__(self, ui, file, line):
        Breakpoint.__init__(self, ui)
        self.file = file
        self.line = line

    def get_line(self):
        return self.line

    def set_line(self, line):
        self.line = int(line)

    def get_file(self):
        return self.file

    def get_cmd(self):
        return '-t {} -f "{}" -n {} -s {}'.format(
            self.type, self.file.as_remote(), self.line, "enabled" if self.enabled else "disabled")


class TemporaryLineBreakpoint(LineBreakpoint):
    def on_add(self):
        pass

    def on_remove(self):
        pass

    def get_cmd(self):
        cmd = LineBreakpoint.get_cmd(self)
        return cmd + " -r 1"


class ConditionalBreakpoint(LineBreakpoint):
    type = "conditional"

    def __init__(self, ui, file, line, condition):
        LineBreakpoint.__init__(self, ui, file, line)
        self.condition = condition

    def get_cmd(self):
        cmd = LineBreakpoint.get_cmd(self)
        cmd += " -- " + base64.encodebytes(
            self.condition.encode("UTF-8")).decode("UTF-8")
        return cmd


class WatchBreakpoint(Breakpoint):
    type = "watch"

    def __init__(self, ui, expr):
        Breakpoint.__init__(self, ui)
        self.expr = expr

    def get_cmd(self):
        cmd = "-t " + self.type
        cmd += " -- " + base64.encodebytes(self.expr)
        return cmd


class ExceptionBreakpoint(Breakpoint):
    type = "exception"

    def __init__(self, ui, exception):
        Breakpoint.__init__(self, ui)
        self.exception = exception

    def get_cmd(self):
        return "-t {} -x {} -s enabled".format(self.type, self.exception)


class CallBreakpoint(Breakpoint):
    type = "call"

    def __init__(self, ui, function):
        Breakpoint.__init__(self, ui)
        self.function = function

    def get_cmd(self):
        return "-t {} -m {} -s enabled".format(self.type, self.function)


class ReturnBreakpoint(CallBreakpoint):
    type = "return"
