import vimui.window
import vim

class Ui():
    """Ui layer which manages the Vim windows.
    """

    def __init__(self):
        self.is_open = False

    def __del__(self):
        self.close()

    def open(self):
        self.is_open = True
        vim.command('silent tabnew')
        
        srcwin_name = self.__get_srcwin_name()

        self.tabnr = vim.eval("tabpagenr()")
        self.watchwin = vimui.window.WatchWindow(self,'vertical belowright new')
        self.stackwin = vimui.window.StackWindow(self,'belowright 6new')
        self.tracewin = vimui.window.TraceWindow(self,'rightbelow 4new')
        
        winnr = self.__get_srcwinno_by_name(srcwin_name)
        self.mainwin = vimui.window.SourceWindow(self,winnr)
        

    def __get_srcwin_name(self):
        return vim.windows[0].buffer.name

    def __get_srcwinno_by_name(self,name):
        i = 1
        for w in vim.windows:
            if w.buffer.name == name:
                break
            else:
                i += 1
        return i

    def say(self,string):
        vim.command('echo "'+string+'"')

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        self.watchwin.destroy()
        self.stackwin.destroy()
        self.tracewin.destroy()

        vim.command('silent '+self.tabnr+'tabc')

        self.watchwin = None
        self.stackwin = None
        self.tracewin = None
