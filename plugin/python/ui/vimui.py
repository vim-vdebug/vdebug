# coding=utf-8
import ui.interface
import vim
import log
import base64

class Ui(ui.interface.Ui):
    """Ui layer which manages the Vim windows.
    """

    def open(self):
        if self.is_open:
            return
        self.is_open = True
        vim.command('silent tabnew')
        
        srcwin_name = self.__get_srcwin_name()

        self.tabnr = vim.eval("tabpagenr()")

        self.watchwin = WatchWindow(self,'vertical belowright new')
        self.watchwin.create()

        self.stackwin = StackWindow(self,'belowright 8new')
        self.stackwin.create()

        self.statuswin = StatusWindow(self,'belowright 5new')
        self.statuswin.create()
        self.statuswin.set_status("loading")

        logwin = LogWindow(self,'rightbelow 6new')
        log.Log.set_logger(log.WindowLogger(\
                log.Logger.DEBUG,\
                logwin))

        winnr = self.__get_srcwinno_by_name(srcwin_name)
        self.sourcewin = SourceWindow(self,winnr)
        self.sourcewin.focus()


    def get_current_file(self):
        return vim.current.buffer.name

    def get_current_row(self):
        return vim.current.window.cursor[0]

    def place_breakpoint(self,sign_id,file,line):
        vim.command('sign place '+str(sign_id)+\
                ' name=breakpt line='+str(line)+\
                ' file='+file)

    def remove_breakpoint(self,sign_id):
        log.Log("Removing breakpoint sign ID %i " % sign_id)
        vim.command('sign unplace '+str(sign_id))

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
        print str(string)
        log.Log(string,log.Logger.INFO)

    def error(self,string):
        vim.command('echohl Error | echo "'+str(string)+'" | echohl None')
        log.Log(string,log.Logger.ERROR)

    def close(self):
        if not self.is_open:
            return
        self.is_open = False

        if self.sourcewin:
            self.sourcewin.clear_signs()

        self.watchwin.destroy()
        self.stackwin.destroy()
        self.statuswin.destroy()

        log.Log.shutdown()

        vim.command('silent! '+self.tabnr+'tabc!')

        self.watchwin = None
        self.stackwin = None
        self.statuswin = None

class SourceWindow(ui.interface.Window):

    file = None
    pointer_sign_id = '6145'
    breakpoint_sign_id = '6146'

    def __init__(self,ui,winno):
        self.winno = str(winno)

    def focus(self):
        vim.command(self.winno+"wincmd w")

    def command(self,cmd,silent = True):
        self.focus()
        prepend = "silent " if silent else ""
        command_str = prepend + self.winno + "wincmd " + cmd
        #print "Executing command: '"+command_str+"'"
        vim.command(command_str)

    def set_file(self,file):
        if file.startswith("file://"):
            file = file[7:]
        self.file = file
        log.Log("Setting source file: "+file,log.Logger.INFO)
        self.focus()
        vim.command("silent edit " + file)

    def clear_signs(self):
        vim.command('sign unplace *')


    def place_pointer(self,line):
        log.Log("Placing pointer sign on line "+str(line),\
                log.Logger.INFO)
        self.remove_pointer()
        vim.command('sign place '+self.pointer_sign_id+\
                ' name=current line='+str(line)+\
                ' file='+self.file)

    def remove_pointer(self):
        vim.command('sign unplace %s' % self.pointer_sign_id)

class Window(ui.interface.Window):
    name = "WINDOW"
    open_cmd = "new"

    def __init__(self,ui,open_cmd):
        self.buffer = None
        self.ui = ui
        self.open_cmd = open_cmd

    def getwinnr(self):
        return int(vim.eval("bufwinnr('"+self.name+"')"))

    def lock(self):
        self.command('setlocal nomodifiable')

    def unlock(self):
        self.command('setlocal modifiable')

    def write(self, msg, return_focus = True, after = "normal G"):
        """ append last """
        """if type(msg) is unicode:
          msg =
          unicodedata.normalize('NFKD',msg).encode('ascii','ignore')"""
        if return_focus:
            prev_win = vim.eval('winnr()')
        self.unlock()
        if self.buffer_empty():
            self.buffer[:] = str(msg).split('\n')
        else:
            self.buffer.append(str(msg).split('\n'))
        self.lock()
        self.command(after)
        if return_focus:
            vim.command('%swincmd W' % prev_win)
        #self.window.cursor = (len(self.buffer), 1)

    def insert(self, msg, lineno = None, overwrite = False, allowEmpty = False):
        """ insert into current position in buffer"""
        if len(msg) == 0 and allowEmpty == False:
            return
        self.unlock()
        if self.buffer_empty():
            self.buffer[:] = str(msg).split('\n')
        else:
            if lineno == None:
                (lineno, rol) = vim.current.window.cursor
            remaining_buffer = str(msg).split('\n')
            if overwrite:
                lfrom = lineno + 1
            else:
                lfrom = lineno
            remaining_buffer.extend(self.buffer[lfrom:])
            del self.buffer[lineno:]
            if self.buffer_empty():
                self.buffer[:] = remaining_buffer
            else:
                for line in remaining_buffer:
                    self.buffer.append(line)
        self.lock()

    def buffer_empty(self):
        if len(self.buffer) == 1 \
                and len(self.buffer[0]) == 0:
            return True
        else:
            return False

    def create(self):
        """ create window """
        vim.command('silent ' + self.open_cmd + ' ' + self.name)
        #if self.name != 'LOG___WINDOW':
        vim.command("setlocal buftype=nofile nomodifiable "+ \
                "winfixheight winfixwidth")
        self.buffer = vim.current.buffer
        self.width  = int( vim.eval("winwidth(0)")  )
        self.height = int( vim.eval("winheight(0)") )
        self.is_open = True
        self.on_create()

    def destroy(self):
        """ destroy window """
        if self.buffer == None or len(dir(self.buffer)) == 0:
            return
        #if self.name == 'LOG___WINDOW':
        #  self.command('hide')
        #else:
        self.command('bwipeout ' + self.name)

    def clean(self):
        """ clean all datas in buffer """
        self.unlock()
        self.buffer[:] = []
        self.lock()

    def command(self, cmd):
        """ go to my window & execute command """
        winnr = self.getwinnr()
        if winnr != int(vim.eval("winnr()")):
            vim.command(str(winnr) + 'wincmd w')
        vim.command(cmd)

    def accept_renderer(self,renderer):
        self.write(renderer.render())

class LogWindow(Window):
    name = "Log"
    def write(self, msg, return_focus = True):
        Window.write(self, msg,return_focus=True)

class StackWindow(Window):
    name = "Stack"
    def write(self, msg, return_focus = True):
        Window.write(self, msg, after="normal gg")

class WatchWindow(Window):
    name = "Watch"

    def write(self, msg, return_focus = True):
        Window.write(self, msg, after="normal gg")

class StatusWindow(Window):
    name = "Status"

    def on_create(self):
        self.write("Status: \n\nPress <F5> to start "+\
                "debugging, <F6> to stop/close.\nType "+\
                ":help vim-debugger for more information.")

    def set_status(self,status):
        self.insert("Status: "+str(status),0,True)

class ResponseRenderer:
    def __init__(self,response):
        self.response = response

    def render(self):
        pass

class StackGetResponseRenderer(ResponseRenderer):
    def render(self):
        stack = self.response.get_stack()
        string = ""
        for s in stack:
            file = s.get('filename')[7:]
            line = "[%(num)s] %(where)s\t\t%(file)s:%(line)s" \
                    %{'num':s.get('level'),'where':s.get('where'),\
                    'file':file,'line':s.get('lineno')}
            string += line + "\n"
        return string

class ContextProperty:

    def __init__(self,node,parent = None,depth = 0):
        self.parent = parent
        self.display_name = node.get('fullname')
        self.type = node.get('type')
        self.encoding = node.get('encoding')
        self.depth = depth
        self.size = node.get('size')
        self.value = ""
        self.is_last_child = False

        children = node.get('children')
        self.num_declared_children = children
        if children is None:
            children = 0
        else:
            children = int(children)
        self.has_children = True if children > 0 else False
        self.children = []

        if self.encoding == 'base64':
            if node.text is None:
                self.value = ""
            else:
                self.value = base64.decodestring(node.text)
        elif not self.is_uninitialized() \
                and not self.has_children:
            self.value = node.text

        if self.value is None:
            self.value = ""

        self.num_crs = self.value.count('\n')
        if self.type == "string":
            self.value = '"%s"' % self.value.replace('"','\\"')

        if self.has_children:
            idx = 0
            for c in node.getchildren():
                idx += 1
                p = ContextProperty(c,self,depth+1)
                self.children.append(p)
                if idx == self.num_declared_children:
                    p.mark_as_last_child()

    def mark_as_last_child(self):
        self.is_last_child = True

    def is_uninitialized(self):
        if self.type == 'uninitialized':
            return True
        else:
            return False

    def marker(self):
        char = "⬦"
        if self.has_children:
            if self.child_count() == 0:
                char = "▸"
            else:
                char = "▾"
        return char

    def child_count(self):
        return len(self.children)

    def type_and_size(self):
        size = None
        if self.has_children:
            size = self.num_declared_children
        elif self.size is not None:
            size = self.size

        if size is None:
            return self.type
        else:
            return "%s [%s]" %(self.type,size)


class ContextGetResponseRenderer(ResponseRenderer):

    def __init__(self,response):
        ResponseRenderer.__init__(self,response)

    def render(self,indent = 0):
        context = self.response.get_context()
        string = ""
        properties = []
        for c in context:
            self.__create_properties(ContextProperty(c),properties)
        
        num_props = len(properties)
        log.Log("Writing %i properties to the context window" % num_props,\
                log.Logger.INFO )

        for idx, prop in enumerate(properties):
            final = False
            try:
                next_prop = properties[idx+1]
            except IndexError:
                final = True
                next_prop = None
            string += self.__render_property(prop,next_prop,final,indent)

        return string

    def __create_properties(self,property,properties):
        properties.append(property)
        for p in property.children:
            self.__create_properties(p,properties)

    def __render_property(self,p,next_p,last = False,indent = 0):
        line = "%(indent)s %(marker)s %(name)s = (%(type)s) %(value)s\n" \
                %{'indent':"".rjust((p.depth * 2)+indent),\
                'marker':p.marker(),'name':p.display_name,\
                'type':p.type_and_size(),'value':p.value}

        depth = p.depth
        if next_p:
            next_depth = next_p.depth
            if depth == next_depth:
                next_sep = "|"
                num_spaces = depth * 2
            elif depth > next_depth:
                next_sep = "/"
                num_spaces = (depth * 2) - 1
            else:
                next_sep = "\\"
                num_spaces = (depth * 2) + 1

            line += "".rjust(num_spaces+indent) + " " + next_sep + "\n"
        elif indent > 0 and last:
            line += "".rjust((depth * 2) - 1 + indent) + " /" + "\n"

        return line
