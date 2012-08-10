# coding=utf-8
import vdebug.log
import vim
import re

class Dispatcher:
    def __init__(self,runner):
        self.runner = runner

    def by_position(self):
        event = self._get_event_by_position()
        if event is not None:
            return event.execute(self.runner)
        else:
            return False

    def _get_event_by_position(self):
        buf_name = vim.current.buffer.name
        p = re.compile("[/\\]([^/\\]+)$")
        m = p.match(buf_name)
        if m is None:
            return None

        window_name = m.group(1)
        if window_name == self.runner.ui.watchwin.name:
            lineno = vim.current.window.cursor[0]
            vdebug.log.Log("User action in watch window, line %s" % lineno,\
                    vdebug.log.Logger.DEBUG)
            line = self.ui.watchwin.buffer[lineno-1]
            if lineno == 1:
                return WatchWindowContextChangeEvent()
            elif line.find("▸"):
                return WatchWindowPropertyGetEvent()
        elif window_name == self.runner.ui.stackwin.name:
            return StackWindowLineSelectEvent()

class Event:
    def execute(self,runner):
        pass

class StackWindowLineSelectEvent(Event):
    def execute(self,runner):
        lineno = vim.current.window.cursor[0]

        vdebug.log.Log("User action in stack window, line %s" % lineno,\
                vdebug.log.Logger.DEBUG)
        line = runner.ui.stackwin.buffer[lineno-1]
        filename_pos = line.find(" @ ") + 3
        file_and_line = line[filename_pos:]
        line_pos = file_and_line.find(":")
        file = vdebug.util.FilePath(file_and_line[:line_pos])
        lineno = file_and_line[line_pos+1:]
        runner.ui.sourcewin.set_file(file)
        runner.ui.sourcewin.set_line(lineno)

class WatchWindowPropertyGetEvent(Event):
    def execute(self,runner):
        lineno = vim.current.window.cursor[0]
        line = vim.current.buffer[lineno]
        pointer_index = line.find("▸")

        eq_index = line.find('=')
        name = line[pointer_index+4:eq_index-1]
        context_res = runner.api.property_get(name)
        rend = vdebug.ui.vimui.ContextGetResponseRenderer(context_res)
        output = rend.render(pointer_index - 1)
        runner.ui.watchwin.insert(output.rstrip(),lineno-1,True)


class WatchWindowContextChangeEvent(Event):
    """Event used to trigger a watch window context change.

    The word under the VIM cursor is retrieved, and context_get called with the
    new context name.
    """

    def execute(self,runner):
        column = vim.current.window.cursor[1]
        line = vim.current.buffer[0]

        vdebug.log.Log("Finding context name at column %s" % column,\
                vdebug.log.Logger.DEBUG)

        tab_end_pos = self.__get_word_end(line,column)
        tab_start_pos = self.__get_word_start(line,column)

        if tab_end_pos == -1 or \
                tab_start_pos == -1:
            raise EventError, "Failed to find context name under cursor"

        context_name = line[tab_start_pos:tab_end_pos]
        vdebug.log.Log("Context name: %s" % context_name,\
                vdebug.log.Logger.DEBUG)
        if context_name[0] == '*':
            runner.ui.say("This context is already showing")
            return False

        context_id = self.__determine_context_id(\
                runner.context_names,context_name)

        if context_id == -1:
            raise EventError, "Could not resolve context name"
            return False
        else:
            runner.get_context(context_id)
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

    def __get_word_start(self,line,column):
        tab_start_pos = -1
        j = column
        while j >= 0:
            if line[j] == '[':
                tab_start_pos = j+2
                break
            j -= 1
        return tab_start_pos

    def __determine_context_id(self,context_names,context_name):
        found_id = -1
        for id in context_names.keys():
            name = context_names[id]
            vdebug.log.Log(name +", "+context_name)
            if name == context_name:
                found_id = id
                break
        return found_id

class EventError(Exception):
    pass
