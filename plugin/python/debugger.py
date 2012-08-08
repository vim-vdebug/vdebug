# coding=utf-8
import sys
import os
import inspect

dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(dir)

import traceback
import dbgp
import log
import ui.vimui
import vim
import breakpoint

class DebuggerInterface:
    """ Acts as an interface, and as an extra layer above the Runner class.

    Fatal exceptions are caught and handled here.
    """
    def __init__(self):
        self.runner = Runner()

    def __del__(self):
        self.runner.close()

    def handle_timeout(self):
        self.runner.close()
        self.runner.ui.say("No connection was made")

    def handle_socket_end(self):
        self.runner.ui.say("Connection to the debugger has been closed")
        if self.runner.ui.is_open:
            self.runner.ui.statuswin.set_status("stopped")

    def handle_vim_error(self,e):
        self.runner.ui.error("A Vim error occured: "+\
                str(e)+\
                "\n"+ traceback.format_exc())

    def handle_helpful_error(self,e):
        self.runner.ui.error(str(e))

    def handle_general_exception(self):
        self.runner.ui.error("An error occured: "+\
                str(sys.exc_info()[0])+\
                "\n"+ traceback.format_exc())

    def run(self):
        try:
            self.runner.run()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except log.LogError, e:
            self.handle_helpful_error(e)
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def run_to_cursor(self):
        try:
            self.runner.run_to_cursor()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except log.LogError, e:
            self.handle_helpful_error(e)
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def handle_return_keypress(self):
        try:
            return self.runner.handle_return_keypress()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def handle_visual_eval(self):
        try:
            return self.runner.handle_visual_eval()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def handle_eval(self,args):
        try:
            return self.runner.eval(args)
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def toggle_breakpoint_window(self):
        return self.runner.toggle_breakpoint_window()

    def step_over(self):
        try:
            self.runner.step_over()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except log.LogError, e:
            self.handle_helpful_error(e)
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def step_into(self):
        try:
            self.runner.step_into()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except log.LogError, e:
            self.handle_helpful_error(e)
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def step_out(self):
        try:
            self.runner.step_over()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except log.LogError, e:
            self.handle_helpful_error(e)
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def set_breakpoint(self,args = None):
        try:
            self.runner.set_breakpoint(args)
        except breakpoint.BreakpointError, e:
            self.runner.ui.error(e)
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def remove_breakpoint(self,args = None):
        try:
            self.runner.remove_breakpoint(args)
        except breakpoint.BreakpointError, e:
            self.runner.ui.error(e)
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def detach(self):
        try:
            self.runner.detach()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.handle_vim_error(e)
        except:
            self.handle_general_exception()

    def close(self):
        if self.runner.is_alive():
            self.runner.close_connection()
        else:
            self.runner.close()

    
class Runner:
    """ Class that stitches together all the debugger components.

    This instantiates the connection and debugger UI, and provides
    an interface that Vim can use to send commands.
    """

    def __init__(self):
        self.api = None
        self.breakpoints = breakpoint.Store()
        self.ui = ui.vimui.Ui(self.breakpoints)

    def open(self):
        """ Open the connection and debugging UI.

        If either of these are already open, the current
        connection or UI is used.
        """
        self.options = vim.eval('g:debugger_options')
        if len(self.options['debug_file']):
            log.Log.set_logger(log.FileLogger(\
                    self.options['debug_file_level'],\
                    self.options['debug_file']))
        self.listen(\
                self.options['server'],\
                int(self.options['port']),\
                int(self.options['timeout']))
        self.ui.open(self.options)
        self.ui.set_listener_details(self.options['server'],self.options['port'])
        addr = self.api.conn.address
        log.Log("Found connection from " + str(addr),log.Logger.INFO)
        self.ui.set_conn_details(addr[0],addr[1])
        self.breakpoints.link_api(self.api)
        status = self.api.step_into()
        self.refresh(status)

    def refresh(self,status):
        """The main action performed after a deubugger step.
    
        Updates the status window, current stack, source
        file and line and watch window."""    
        if not self.is_alive():
            self.ui.error("Cannot update: no connection")
        else:

            if str(status) in ("stopping","stopped"):
                self.ui.statuswin.set_status("stopped")
                self.ui.say("Debugging session has ended")
                self.close_connection()
            else:
                log.Log("Getting stack information")
                self.ui.statuswin.set_status(status)
                stack_res = self.update_stack()
                stack = stack_res.get_stack()

                filename = stack[0].get('filename')
                lineno = stack[0].get('lineno')

                log.Log("Moving to current position in source window")
                self.ui.sourcewin.set_file(filename)
                self.ui.sourcewin.set_line(lineno)
                self.ui.sourcewin.place_pointer(lineno)

                self.ui.watchwin.clean()
                log.Log("Getting context variables")
                context_res = self.api.context_get()
                rend = ui.vimui.ContextGetResponseRenderer(\
                        context_res,"Context at %s:%s" \
                        %(self.ui.sourcewin.file,lineno))
                self.ui.watchwin.accept_renderer(rend)

    def toggle_breakpoint_window(self):
        """Open or close the breakpoint window.

        The window appears as a horizontal split below the
        currently selected window."""
        if self.ui.breakpointwin.is_open:
            self.ui.breakpointwin.destroy()
        else:
            self.ui.breakpointwin.create()

    def is_alive(self):
        """Whether the connection is open."""
        if self.api is not None and \
            self.api.conn.isconnected():
                return True
        return False

    def run(self):
        """Tell the debugger to run.

        It will run until the end of the execution or until a
        breakpoint is reached."""
        if not self.is_alive():
            self.open()
        else:
            log.Log("Running")
            self.ui.statuswin.set_status("running")
            self.ui.sourcewin.remove_pointer()
            res = self.api.run()
            self.refresh(res)

    def step_over(self):
        """Step over to the next statement."""
        if not self.is_alive():
            self.open()
        else:
            log.Log("Stepping over")
            self.ui.statuswin.set_status("running")
            self.ui.sourcewin.remove_pointer()
            res = self.api.step_over()
            self.refresh(res)

    def step_into(self):
        """Step into the next statement."""
        if not self.is_alive():
            self.open()
        else:
            log.Log("Stepping into statement")
            self.ui.statuswin.set_status("running")
            self.ui.sourcewin.remove_pointer()
            res = self.api.step_into()
            self.refresh(res)

    def step_out(self):
        """Step out of the current context."""
        if not self.is_alive():
            self.open()
        else:
            log.Log("Stepping out of statement")
            self.ui.statuswin.set_status("running")
            self.ui.sourcewin.remove_pointer()
            res = self.api.step_out()
            self.refresh(res)

    def remove_breakpoint(self,args):
        """Remove a breakpoint, by ID or "*"."""
        if args is None:
            args = ""
        args = args.strip()
        if len(args) == 0:
            self.ui.error("ID or '*' required to remove a breakpoint: run "+\
                    "':BreakpointWindow' to see breakpoints and their IDs")
            return

        if args == '*':
            self.breakpoints.clear_breakpoints()
        else:
            arg_parts = args.split(" ")
            for id in arg_parts:
                self.breakpoints.remove_breakpoint_by_id(id)

    def set_breakpoint(self,args):
        bp = breakpoint.Breakpoint.parse(self.ui,args)
        if bp.type == "line":
            id = self.breakpoints.find_breakpoint(\
                    bp.get_file(),\
                    bp.get_line())
            if id is not None:
                self.breakpoints.remove_breakpoint_by_id(id)
                return
        self.breakpoints.add_breakpoint(bp)

    def eval(self,code):
        log.Log("Evaluating code: "+code)
        context_res = self.api.eval(code)
        rend = ui.vimui.ContextGetResponseRenderer(\
                context_res,"Eval of: '%s'" \
                %context_res.get_code())
        self.ui.watchwin.clean()
        self.ui.watchwin.accept_renderer(rend)

    def handle_visual_eval(self):
        selection = vim.eval("debugger:get_visual_selection()")
        self.eval(selection)

    def run_to_cursor(self):
        row = self.ui.get_current_row()
        file = self.ui.get_current_file()
        if file != self.ui.sourcewin.get_file():
            self.ui.error("Run to cursor only works in the source window!")
            return
        log.Log("Running to position: line %s of %s" %(row,file))
        bp = breakpoint.TemporaryLineBreakpoint(self.ui,file,row)
        self.api.breakpoint_set(bp.get_cmd())
        self.run()

    def handle_return_keypress(self):
        """ Handle what happens when the user hits return."""
        if not self.is_alive():
            return True
        lineno = vim.current.window.cursor[0]
        if self.ui.watchwin.name in vim.current.buffer.name:
            log.Log("User action in watch window, line %s" % lineno,\
                    log.Logger.DEBUG)
            line = self.ui.watchwin.buffer[lineno-1]
            index = line.find("▸")
            if index > 0:
                self.handle_property_get(lineno,line,index)
        if self.ui.stackwin.name in vim.current.buffer.name:
            log.Log("User action in stack window, line %s" % lineno,\
                    log.Logger.DEBUG)
            line = self.ui.stackwin.buffer[lineno-1]
            filename_pos = line.find("\t\t")
            file_and_line = line[filename_pos:]
            line_pos = file_and_line.find(":")
            file = file_and_line[:line_pos]
            lineno = file_and_line[line_pos+1:]
            self.ui.sourcewin.set_file(file)
            self.ui.sourcewin.set_line(lineno)

    def handle_property_get(self,lineno,line,pointer_index):
        eq_index = line.find('=')
        name = line[pointer_index+4:eq_index-1]
        context_res = self.api.property_get(name)
        rend = ui.vimui.ContextGetResponseRenderer(context_res)
        output = rend.render(pointer_index - 1)
        self.ui.watchwin.insert(output.rstrip(),lineno-1,True)

    def listen(self,server,port,timeout):
        """ Open the dbgp API with connection.

        Uses existing connection if possible.
        """
        if self.is_alive():
            log.Log("Cannot open a new connection \
                while one already exists",\
                log.Logger.ERROR)
            return
        else:
            connection = dbgp.Connection(server,port,timeout)
            self.api = dbgp.Api(connection)

    def update_stack(self):
        if not self.is_alive():
            self.ui.error("Cannot update the stack: no debugger connection")
        else:
            self.ui.stackwin.clean()
            res = self.api.stack_get()
            renderer = ui.vimui.StackGetResponseRenderer(res)
            self.ui.stackwin.accept_renderer(renderer)
            return res

    def detach(self):
        if not self.is_alive():
            self.ui.error("Cannot detach: no debugger connection")
        else:
            self.say("Detaching the debugger")
            self.api.detach()

    def close_connection(self):
        """ Close the connection to the debugger.
        """
        try:
            if self.is_alive():
                self.breakpoints.unlink_api()
                if self.options['on_close'] == 'detach':
                    self.api.detach()
                else:
                    self.api.stop()
                self.api.conn.close()
                self.ui.sourcewin.remove_pointer()
                self.ui.statuswin.set_status("stopped")
                self.ui.remove_conn_details()
            self.api = None
        except EOFError:
            self.ui.say("Connection has been closed")
            if self.ui.is_open:
                self.ui.statuswin.set_status("stopped")

    def close(self):
        """ Close both the connection and UI.
        """
        self.close_connection()
        self.ui.close()

vdebug = DebuggerInterface()
