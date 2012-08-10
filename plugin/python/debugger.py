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
import opts
import util

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
        except KeyboardInterrupt:
            print "Keyboard interrupt - debugging session cancelled"
            try:
                self.runner.close()
            except:
                pass
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
            self.runner.step_out()
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
        opts.Options.set(vim.eval('g:debugger_options'))
        if opts.Options.isset('debug_file'):
            log.Log.set_logger(log.FileLogger(\
                    opts.Options.get('debug_file_level'),\
                    opts.Options.get('debug_file')))
        self.listen(\
                opts.Options.get('server'),\
                opts.Options.get('port',int),\
                opts.Options.get('timeout',int))

        self.ui.open()
        self.ui.set_listener_details(\
                opts.Options.get('server'),\
                opts.Options.get('port'),\
                opts.Options.get('ide_key'))

        addr = self.api.conn.address
        log.Log("Found connection from " + str(addr),log.Logger.INFO)
        self.ui.set_conn_details(addr[0],addr[1])
        self.breakpoints.link_api(self.api)

        cn_res = self.api.context_names()
        self.context_names = cn_res.names()
        log.Log("Available context names: %s" %\
                str(self.context_names),log.Logger.DEBUG)

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

                self.cur_file = util.FilePath(stack[0].get('filename'))
                self.cur_lineno = stack[0].get('lineno')

                log.Log("Moving to current position in source window")
                self.ui.set_source_position(\
                        self.cur_file,\
                        self.cur_lineno)

                self.get_context(0)

    def get_context(self,context_id = 0):
        self.ui.watchwin.clean()
        name = self.context_names[context_id]
        log.Log("Getting %s variables" % name)
        context_res = self.api.context_get(context_id)
        rend = ui.vimui.ContextGetResponseRenderer(\
                context_res,"%s at %s:%s" \
                %(name,self.ui.sourcewin.file,self.cur_lineno),\
                self.context_names, context_id)
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
        selection = vim.eval("vdebug:get_visual_selection()")
        self.eval(selection)

    def run_to_cursor(self):
        row = self.ui.get_current_row()
        file = self.ui.get_current_file()
        log.Log(file)
        log.Log(self.ui.sourcewin.get_file())
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
            if lineno == 1:
                self.handle_context_change(\
                    line,vim.current.window.cursor[1])
            else:
                index = line.find("▸")
                if index > 0:
                    self.handle_property_get(lineno,line,index)
        elif self.ui.stackwin.name in vim.current.buffer.name:
            log.Log("User action in stack window, line %s" % lineno,\
                    log.Logger.DEBUG)
            line = self.ui.stackwin.buffer[lineno-1]
            filename_pos = line.find("\t\t")
            file_and_line = line[filename_pos:]
            line_pos = file_and_line.find(":")
            file = util.FilePath(file_and_line[:line_pos])
            lineno = file_and_line[line_pos+1:]
            self.ui.sourcewin.set_file(file)
            self.ui.sourcewin.set_line(lineno)

    def handle_context_change(self,line,column):
        log.Log("Finding context name at column %s" % column,\
                log.Logger.DEBUG)
        tab_end_pos = -1
        tab_start_pos = -1

        line_len = len(line)
        i = column
        while i < line_len:
            if line[i] == ']':
                tab_end_pos = i-1
                break
            i += 1
        j = column
        while j >= 0:
            if line[j] == '[':
                tab_start_pos = j+2
                break
            j -= 1
        if tab_end_pos == -1 or \
                tab_start_pos == -1:
            self.ui.error("Failed to find context name under cursor")
            return
        context_name = line[tab_start_pos:tab_end_pos]
        log.Log("Context name: %s" % context_name,\
                log.Logger.DEBUG)
        if context_name[0] == '*':
            self.ui.say("This context is already showing")
            return
        found_id = -1
        for id in self.context_names.keys():
            name = self.context_names[id]
            log.Log(name +", "+context_name)
            if name == context_name:
                found_id = id
                break
        if found_id == -1:
            self.ui.error("Could not resolve context name")
            return
        else:
            self.get_context(found_id)
            

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
            while True:
                    ide_key = opts.Options.get('ide_key')
                    check_ide_key = True
                    if len(ide_key) == 0:
                        check_ide_key = False
                    connection = dbgp.Connection(server,port,timeout)
                    self.api = dbgp.Api(connection)
                    if check_ide_key and ide_key != self.api.idekey:
                        print "Ignoring debugger connection with IDE key '%s'" \
                                % self.api.idekey
                        self.api.detach()
                    else:
                        break

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
                if opts.Options.get('on_close') == 'detach':
                    self.api.detach()
                else:
                    self.api.stop()
                self.api.conn.close()
                self.ui.mark_as_stopped()
                
            self.api = None
        except EOFError:
            self.ui.say("Connection has been closed")
            self.ui.mark_as_stopped()

    def close(self):
        """ Close both the connection and UI.
        """
        self.close_connection()
        self.ui.close()
