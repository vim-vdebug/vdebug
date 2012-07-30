import base64
import vim
import log

class Store:

    def __init__(self):
        self.breakpoints = {}
        self.api = None

    def link_api(self,api):
        self.api = api
        log.Log("Registering "+str(len(self.breakpoints))+\
                " breakpoints with the debugger",\
                log.Logger.DEBUG)
        for id, bp in self.breakpoints.iteritems():
            self.api.breakpoint_set(bp.get_cmd())


    def unlink_api(self):
        self.api = None

    def add_breakpoint(self,breakpoint):
        log.Log("Adding breakpoint "+\
                str(breakpoint),\
                log.Logger.DEBUG)
        self.breakpoints[str(breakpoint.get_id())] = breakpoint
        breakpoint.on_add()
        if self.api is not None:
            self.api.breakpoint_set(breakpoint.get_cmd())

    def remove_breakpoint(self,breakpoint):
        self.remove_breakpoint_by_id(\
                breakpoint.get_id())

    def remove_breakpoint_by_id(self,id):
        id = str(id)
        log.Log("Removing breakpoint "+\
                str(self.breakpoints[id]),\
                log.Logger.DEBUG)
        self.breakpoints[id].on_remove()
        del self.breakpoints[id]

    def clear_breakpoints(self):
        for id, bp in self.breakpoints.iteritems():
            self.remove_breakpoint_by_id(id)
        self.breakpoints = {}

    def find_breakpoint(self,file,line):
        found = None
        for id, bp in self.breakpoints.iteritems():
            if bp.type == "line":
                if bp.get_file() == file and\
                        bp.get_line() == line:
                    found = bp.get_id()
                    break
        return found


class Breakpoint:
    type = None
    id = 11000

    def __init__(self,ui):
        self.id = Breakpoint.id
        Breakpoint.id += 1 
        self.ui = ui

    def get_id(self):
        return self.id

    def on_add(self):
        pass

    def on_remove(self):
        pass

    @classmethod
    def parse(self,ui,args):
        args = args.strip()
        if len(args) == 0:
            """ Line breakpoint """
            (row, col) = vim.current.window.cursor
            file       = vim.current.buffer.name
            if file != ui.sourcewin.file:
                raise WrongWindowError
            return LineBreakpoint(ui,file,row)
        else:
            print "not yet implemented"

    def get_cmd(self):
        pass

    def __str__(self):
        return "["+self.type+"] "+str(self.id)

class LineBreakpoint(Breakpoint):
    type = "line"

    def __init__(self,ui,file,line):
        Breakpoint.__init__(self,ui)
        self.file = file
        self.line = line

    def on_add(self):
        self.ui.sourcewin.place_breakpoint(\
                self.id,\
                self.line)
    
    def on_remove(self):
        self.ui.sourcewin.remove_breakpoint(\
                self.id,\
                self.line)

    def get_line(self):
        return self.line

    def get_file(self):
        return self.file

    def get_cmd(self):
        cmd = "-t " + self.type
        cmd += " -f " + self.file
        cmd += " -n " + str(self.line)
        return cmd

class ConditionalBreakpoint(LineBreakpoint):
    type = "conditional"

    def __init__(self,ui,file,line,condition):
        LineBreakpoint.__init__(self,ui,file,line)
        self.condition = condition

    def get_cmd(self):
        cmd = LineBreakpoint.get_cmd(self)
        cmd += " -- " + base64.encodestring(self.condition)
        return cmd

class WrongWindowError(Exception):
    pass
