import ui.vim.window
import ui.interface
import vim
import log

class Ui(ui.interface.Ui):
    """Ui layer which manages the Vim windows.
    """

    def open(self):
        self.is_open = True
        vim.command('silent tabnew')
        
        srcwin_name = self.__get_srcwin_name()

        self.tabnr = vim.eval("tabpagenr()")
        self.watchwin = ui.vim.window.WatchWindow(self,'vertical belowright new')
        self.stackwin = ui.vim.window.StackWindow(self,'belowright 6new')
        logwin = ui.vim.window.LogWindow(self,'rightbelow 4new')
        log.Log.set_logger(log.WindowLogger(logwin))
        
        winnr = self.__get_srcwinno_by_name(srcwin_name)
        self.sourcewin = ui.vim.window.SourceWindow(self,winnr)
        log.Log("Monkeys")

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
        """ Vim picks up Python prints, so just print """
        print string

    def error(self,string):
        vim.command('echohl Error | echo "'+string+'" | echohl None')

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        self.watchwin.destroy()
        self.stackwin.destroy()

        log.Log.shutdown()

        vim.command('silent! '+self.tabnr+'tabc!')

        self.watchwin = None
        self.stackwin = None
