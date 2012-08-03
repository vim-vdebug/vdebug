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
    """ Acts as an interface, mainly to the Runner class.

    Exceptions are caught and handled here.
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
        self.runner.ui.statuswin.set_status("stopped")

    def run(self):
        try:
            self.runner.run()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.runner.ui.error(str(e)+"\nTraceback: "+\
                    traceback.format_exc())
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0])+\
                    "\nTraceback: "+\
                    traceback.format_exc())
            #self.runner.close()
            raise

    def handle_watch_toggle(self):
        try:
            self.runner.handle_watch_toggle()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.runner.ui.error(str(e)+"\nTraceback: "+\
                    traceback.format_exc())
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0])+\
                    "\nTraceback: "+\
                    traceback.format_exc())
            #self.runner.close()
            raise

    def step_over(self):
        try:
            self.runner.step_over()
        except dbgp.TimeoutError:
            self.handle_timeout()
        except EOFError:
            self.handle_socket_end()
        except vim.error, e:
            self.runner.ui.error(e)
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0]))
            #self.runner.close()
            raise


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
            self.runner.ui.error(e)
        except:
            self.runner.ui.error("An error occured: "+\
                    str(sys.exc_info()[0]))
            #self.runner.close()
            raise

    def close(self):
        self.runner.close()

    
class Runner:
    """ Class that stitches together all the debugger components.

    This instantiates the connection and debugger UI, and provides
    an interface that Vim can use to send commands.
    """

    def __init__(self):
        self.ui = ui.vimui.Ui()
        self.api = None
        self.breakpoints = breakpoint.Store()

    def open(self,server='',port=9000,timeout=30):
        """ Open the connection and debugging UI.

        If either of these are already open, the current
        connection or UI is used.
        """
        self.listen(server,port,timeout)
        self.ui.open()
        addr = str(self.api.conn.address)
        log.Log("Found connection from " + addr,log.Logger.INFO)
        self.breakpoints.link_api(self.api)
        self.api.step_into()
        self.refresh()

    def refresh(self):
        if not self.is_alive():
            self.ui.error("Cannot update: no connection")
        else:
            status = self.api.status()

            if str(status) in ("stopping","stopped"):
                self.ui.statuswin.set_status("stopped")
                self.ui.say("Debugging session has ended")
                self.close_connection()
            else:
                self.ui.statuswin.set_status(status)
                stack_res = self.update_stack()
                stack = stack_res.get_stack()

                filename = stack[0].get('filename')
                lineno = stack[0].get('lineno')

                self.ui.sourcewin.set_file(filename)
                self.ui.sourcewin.place_pointer(lineno)

                self.ui.watchwin.clean()
                context_res = self.api.context_get()
                rend = ui.vimui.ContextGetResponseRenderer(context_res)
                self.ui.watchwin.accept_renderer(rend)


    def is_alive(self):
        if self.api is not None and \
            self.api.conn.isconnected():
                return True
        return False

    def run(self):
        if not self.is_alive():
            self.open()
        else:
            self.ui.sourcewin.remove_pointer()
            self.ui.statuswin.set_status("running")
            self.api.run()
            self.refresh()

    def step_over(self):
        if not self.is_alive():
            self.open()
        else:
            self.ui.sourcewin.remove_pointer()
            self.api.step_over()
            self.refresh()

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

    def handle_watch_toggle(self):
        """ Return the number of lines that a property block reaches to."""
        if self.ui.watchwin.name not in vim.current.buffer.name:
            return
        log.Log("Current buffer name: "+vim.current.buffer.name)
        lineno = vim.current.window.cursor[0]
        log.Log("Carriage return on line "+str(lineno))
        line = self.ui.watchwin.buffer[lineno-1]
        index = line.find("▸")
        if index > 0:
            self.handle_open(lineno,line,index)
        
    def handle_open(self,lineno,line,pointer_index):
        eq_index = line.find('=')
        name = line[pointer_index+4:eq_index-1]
        context_res = self.api.property_get(name)
        rend = ui.vimui.ContextGetResponseRenderer(context_res)
        output = rend.render(pointer_index - 1)
        log.Log(output)
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
        pass
        if not self.is_alive():
            self.ui.error("Cannot update the stack: no connection")
        else:
            self.ui.stackwin.clean()
            res = self.api.stack_get()
            renderer = ui.vimui.StackGetResponseRenderer(res)
            self.ui.stackwin.accept_renderer(renderer)
            return res

    def close_connection(self):
        """ Close the connection to the debugger.
        """
        try:
            if self.is_alive():
                self.breakpoints.unlink_api()
                self.api.stop()
                self.api.conn.close()
            self.api = None
        except EOFError:
            self.ui.say("Connection has been closed")

    def close(self):
        """ Close both the connection and UI.
        """
        self.close_connection()
        self.ui.close()

vdebug = DebuggerInterface()
