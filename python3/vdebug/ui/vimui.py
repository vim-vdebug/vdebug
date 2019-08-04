# coding=utf-8

import sys

import vim

from . import interface
from .. import log
from .. import opts
from .. import util


class WindowError(Exception):
    pass


class WindowManager:

    def __init__(self):
        self._windows = {
            "DebuggerWatch":  WatchWindow(),
            "DebuggerStack": StackWindow(),
            "DebuggerStatus": StatusWindow(),
            "DebuggerBreakpoints": BreakpointWindow(),
            "DebuggerLog": LogWindow(),
            "DebuggerTrace": TraceWindow()
        }
        self._default_commands = {
            "DebuggerWatch": "vertical belowright new",
            "DebuggerStatus": "belowright new",
            "DebuggerStack": "belowright new",
            "DebuggerBreakpoints": "rightbelow 7new",
            "DebuggerLog": "rightbelow 6new",
            "DebuggerTrace": 'rightbelow 7new'
        }
        self._commands = self._default_commands.copy()
        self._default_layout = {
            'window_commands': {
                'DebuggerWatch': 'vertical belowright new',
                'DebuggerStack': 'aboveleft 12new',
                'DebuggerStatus': 'aboveleft 1new'
            },
            'window_size': {
            },
            'window_arrangement': [
                'DebuggerWatch',
                'DebuggerStack',
                'DebuggerStatus'
            ]
        }
        self._layout = None

    def open_all(self):
        self._refresh_commands()
        layout = self.get_layout()
        arrangement = layout["window_arrangement"]

        for name in arrangement:
            self.window(name).create(self._command(name))

    def open(self, name):
        if not self.window(name).is_open:
            log.Log("Creating window %s" % name)
            self.window(name).create(self._command(name))

    def toggle(self, name):
        self.window(name).toggle(self._command(name))

    def close(self):
        for win in self._windows.values():
            win.destroy()

    def watch(self):
        return self.window("DebuggerWatch")

    def status(self):
        return self.window("DebuggerStatus")

    def stack(self):
        return self.window("DebuggerStack")

    def breakpoints(self):
        return self.window("DebuggerBreakpoints")

    def log(self):
        return self.window("DebuggerLog")

    def trace(self):
        return self.window("DebuggerTrace")

    def window(self, name):
        try:
            return self._windows[name]
        except KeyError:
            raise WindowError("No debugger window named '%s' - check your "
                              "window options" % name)

    def _command(self, name):
        try:
            return self._commands[name]
        except KeyError:
            raise WindowError("No debugger window named '%s' - check your "
                              "window options" % name)

    def set_layout(self, layout):
        self._layout = layout

    def get_layout(self):
        if self._layout is None \
                or 'window_commands' not in self._layout \
                or 'window_arrangement' not in self._layout:
            self.set_layout(self._default_layout)

        return self._layout

    def _refresh_commands(self):
        self._commands = self._default_commands.copy()

        updated_commands = self._layout["window_commands"]
        self._commands.update(updated_commands)


class Ui(interface.Ui):
    """Ui layer which manages the Vim windows.
    """

    def __init__(self):
        interface.Ui.__init__(self)
        self.is_open = False
        self.emptybuffer = None
        self.windows = WindowManager()
        self.current_tab = "1"
        self.tabnr = None
        self._last_error = None
        self.empty_buf_num = None
        self.selected_stack = None
        self.selected_context = 0
        self.default_layout = 'vertical'
        self.layouts = {
            'vertical': {
                'window_commands': {
                    'DebuggerWatch': 'vertical belowright new',
                    'DebuggerStack': 'aboveleft 12new',
                    'DebuggerStatus': 'aboveleft 1new'
                },
                'window_size': {
                },
                'window_arrangement': [
                    'DebuggerWatch',
                    'DebuggerStack',
                    'DebuggerStatus'
                ]
            },
            'horizontal': {
                'window_commands': {
                    'DebuggerWatch': 'below new',
                    'DebuggerStack': 'belowright new',
                    'DebuggerStatus': 'vertical leftabove new'
                },
                'window_size': {
                    'DebuggerWatch': { 'height' : 15 },
                    'DebuggerStatus':  { 'height' : 1 }
                },
                'window_arrangement': [
                    'DebuggerWatch',
                    'DebuggerStatus',
                    'DebuggerStack'
                ]
            }
        }

    def mark_window_as_closed(self, name):
        self.windows.window(name).mark_as_closed()

    def toggle_window(self, name):
        self.windows.toggle(name)

    @staticmethod
    def is_modified():
        return vim.current.buffer.options['modified']

    def window(self, name):
        self.windows.window(name)

    def open(self):
        if self.is_open:
            return
        self.is_open = True

        try:
            layout_option = opts.Options.get('layout', str)

            layout = self.layouts[layout_option] \
                if layout_option in self.layouts \
                else self.layouts[self.default_layout]

            existing_buffer = True
            cur_buf_name = vim.current.buffer.name
            if cur_buf_name is None:
                existing_buffer = False
                cur_buf_name = ''

            self.current_tab = vim.current.tabpage.number

            vim.command('silent tabnew')
            self.empty_buf_num = vim.current.buffer.number
            if existing_buffer:
                vim.command('call Vdebug_edit("%s")' % cur_buf_name)

            self.tabnr = vim.current.tabpage.number

            self.windows.set_layout(layout)
            self.windows.open_all()
            statuswin = self.windows.status()
            statuswin.set_status("loading")

            window_sizes = layout["window_size"] if "window_size" in layout else {}
            for window_name, settings in window_sizes.items():
                if 'height' in settings:
                    self.windows.window(window_name).set_height(settings['height'])
                if 'width' in settings:
                    self.windows.window(window_name).set_width(settings['width'])

            log.Log.set_logger(log.WindowLogger(
                opts.Options.get('debug_window_level'), self.windows.log()))

            self.sourcewin = SourceWindow()
            self.sourcewin.focus()
        except Exception:
            self.is_open = False
            raise

    def set_source_position(self, file, lineno):
        self.sourcewin.set_file(file)
        self.sourcewin.set_line(lineno)
        self.sourcewin.place_pointer(lineno)

    def mark_as_stopped(self):
        if self.is_open:
            if self.sourcewin:
                self.sourcewin.remove_pointer()
            self.windows.status().mark_as_stopped()

    def set_conn_details(self, addr, port):
        self.windows.status().set_conn_details(addr, port)

    def set_listener_details(self, addr, port, idekey):
        self.windows.status().set_listener_details(addr, port, idekey)

    def set_status(self, status):
        self.windows.status().set_status(status)

    @staticmethod
    def get_current_file():
        return util.LocalFilePath(vim.current.buffer.name)

    @staticmethod
    def get_current_row():
        return vim.current.window.cursor[0]

    def get_current_line(self):
        return self.get_line(self.get_current_row())

    @staticmethod
    def get_line(row):
        return vim.current.buffer[row - 1]

    def register_breakpoint(self, breakpoint):
        if breakpoint.type == 'line':
            self.place_breakpoint(breakpoint.id, breakpoint.file,
                                  breakpoint.line)
        self.windows.breakpoints().add_breakpoint(breakpoint)

    @staticmethod
    def place_breakpoint(sign_id, file, line):
        vim.command('sign place %s name=breakpt line=%s file=%s'
                    % (sign_id, line, file.as_local()))

    def enable_breakpoint(self, breakpoint):
        self.place_breakpoint(breakpoint.id, breakpoint.file, breakpoint.line)

    def disable_breakpoint(self, breakpoint):
        self.place_disabled_breakpoint(breakpoint.id, breakpoint.file, breakpoint.line)

    @staticmethod
    def place_disabled_breakpoint(sign_id, file, line):
        vim.command('sign place %s name=breakpt_dis line=%s file=%s'
                    % (sign_id, line, file.as_local()))

    def remove_breakpoint(self, breakpoint):
        id = breakpoint.id
        vim.command('sign unplace %i' % id)
        self.windows.breakpoints().remove_breakpoint(id)

    def get_breakpoint_sign_positions(self):
        sign_lines = self.command('sign place').split("\n")
        positions = {}
        for line in sign_lines:
            if "name=breakpt" in line:
                attributes = line.strip().split()
                lineinfo = attributes[0].split('=')
                idinfo = attributes[1].split('=')
                positions[idinfo[1]] = lineinfo[1]
        return positions

    # Execute a vim command and return the output.
    def command(self, cmd):
        vim.command('redir => _tmp')
        vim.command('silent %s' % cmd)
        vim.command('redir END')
        return vim.eval('_tmp')

    def say(self, string):
        """ Vim picks up Python prints, so just print """
        print(string)
        log.Log(string, log.Logger.INFO)

    def error(self, string):
        self._last_error = string
        print(string, file=sys.stderr)
        log.Log(string, log.Logger.ERROR)

    def get_last_error(self):
        return self._last_error

    def close(self):
        if not self.is_open:
            return
        self.is_open = False

        log.Log.remove_logger('WindowLogger')
        if self.tabnr:
            vim.command('silent! %stabc!' % self.tabnr)
        if self.current_tab:
            vim.command('tabn %s' % self.current_tab)

        if self.empty_buf_num:
            vim.command('bw%s' % self.empty_buf_num)

        self.windows.close()

    @staticmethod
    def __get_buf_list():
        return vim.eval("range(1, bufnr('$'))")


class SourceWindow(interface.Window):

    file = None
    pointer_sign_id = '6145'
    breakpoint_sign_id = '6146'

    def focus(self):
        vim.command("1wincmd w")
        vim.command("filetype detect")

    def command(self, cmd, silent=True):
        self.focus()
        if silent:
            prepend = "silent "
        else:
            prepend = ""
        command_str = prepend + "1wincmd " + cmd
        vim.command(command_str)

    def set_file(self, file):
        if file == self.file:
            return
        self.file = file
        log.Log("Setting source file: %s" % file, log.Logger.INFO)
        self.focus()
        vim.command('call Vdebug_edit("%s")' % str(file).replace("\\", "\\\\"))

    def set_line(self, lineno):
        log.Log("Setting source line number: %s" % lineno, log.Logger.DEBUG)
        self.focus()
        vim.command(":%s" % lineno)

    def get_file(self):
        self.focus()
        self.file = util.LocalFilePath(vim.current.buffer.name)
        return self.file

    def place_pointer(self, line):
        log.Log("Placing pointer sign on line "+str(line), log.Logger.INFO)
        self.remove_pointer()
        vim.command('sign place %s name=current line=%s file=%s'
                    % (self.pointer_sign_id, line, self.file))

    def remove_pointer(self):
        vim.command('sign unplace %s' % self.pointer_sign_id)


class VimBuffer:

    def __init__(self, buffer):
        self._buffer = buffer

    def overwrite(self, content):
        self._buffer[:] = content

    def line(self, number):
        return self._buffer[number]

    def write(self, msg, return_focus, after_callback):
        if return_focus:
            prev_win = vim.current.window.number
        if self.is_empty():
            self._buffer[:] = str(msg).split('\n')
        else:
            self._buffer.append(str(msg).split('\n'))
            after_callback()
            if return_focus:
                vim.command('%swincmd W' % prev_win)

    def insert(self, msg, lineno, overwrite, allowEmpty, after_callback):
        """ insert into current position in buffer"""
        if not msg and not allowEmpty:
            return
        if self.is_empty():
            self._buffer[:] = str(msg).split('\n')
        else:
            if lineno is None:
                lineno, col = vim.current.window.cursor
            remaining_buffer = str(msg).split('\n')
            if overwrite:
                lfrom = lineno + 1
            else:
                lfrom = lineno
            remaining_buffer.extend(self._buffer[lfrom:])
            del self._buffer[lineno:]
            if self.is_empty():
                self._buffer[:] = remaining_buffer
            else:
                for line in remaining_buffer:
                    self._buffer.append(line)
            after_callback()

    def delete(self, start_line, end_line=None):
        try:
            if not end_line:
                end_line = start_line + 1
            self._buffer[end_line]
            remaining_buffer = self._buffer[end_line:]
            del self._buffer[start_line:]
            self._buffer.append(remaining_buffer)
        except IndexError:
            del self._buffer[start_line:]

    def contents(self):
        return self._buffer[:]

    def clean(self):
        self._buffer[:] = []

    def is_empty(self):
        return bool(len(self._buffer) == 1 and not self._buffer[0])


class HiddenBuffer:

    def __init__(self, buffer=None):
        self._buffer = buffer if buffer is not None else []
        log.Log("Creating hidden buffer: %s" % buffer,
                log.Logger.DEBUG)

    def line(self, number):
        return self._buffer[number]

    def write(self, msg, return_focus, after):
        if self.is_empty():
            # If empty
            self._buffer[:] = str(msg).split('\n')
        else:
            # Otherwise add to the end
            self._buffer.extend(str(msg).split('\n'))

    def insert(self, msg, lineno, overwrite, allowEmpty, after_callback):
        """ insert into current position in buffer"""
        if not msg and not allowEmpty:
            return
        if self.is_empty():
            self._buffer[:] = str(msg).split('\n')
        else:
            if overwrite:
                from_line = lineno
                to_line = lineno + 1
            else:
                from_line = lineno
                to_line = lineno
            self._buffer[from_line:to_line] = str(msg).split('\n')
        log.Log("Hidden buffer after insert: %s" % (self._buffer),
                log.Logger.DEBUG)

    def delete(self, start_line, end_line=None):
        try:
            if not end_line:
                end_line = start_line + 1
            self._buffer[start_line:end_line] = []
        except IndexError:
            del self._buffer[start_line:]

    def clean(self):
        self._buffer[:] = []

    def contents(self):
        return self._buffer[:]

    def is_empty(self):
        return not self._buffer


class Window(interface.Window):

    name = "WINDOW"
    creation_count = 0

    def __init__(self):
        self._buffer = HiddenBuffer()
        self.is_open = False

    def toggle(self, open_cmd):
        if self.is_open:
            self.destroy()
        else:
            self.create(open_cmd)

    def mark_as_closed(self):
        self.destroy()

    def getwinnr(self):
        return int(vim.eval("bufwinnr('%s')" % self.name))

    def set_height(self, height):
        height = int(height)
        minheight = int(vim.eval("&winminheight"))
        if height < minheight:
            height = minheight
        if height <= 0:
            height = 1
        self.command('resize %i' % height)

    def set_width(self, width):
        width = int(width)
        if width <= 0:
            width =1
        self.command('vertical resize %i' % width)

    def write(self, msg, return_focus=True, after="normal G"):
        self._buffer.write(msg, return_focus, lambda: self.command(after))

    def insert(self, msg, lineno=None, overwrite=False, allowEmpty=False):
        self._buffer.insert(msg, lineno, overwrite, allowEmpty,
                            lambda: self.command(lineno))

    def delete(self, start_line, end_line=None):
        self._buffer.delete(start_line, end_line)

    def line_at(self, line):
        return self._buffer.line(line)

    def create(self, open_cmd):
        """ create window """
        vim.command('silent %s %s' % (open_cmd, self.name))
        vim.current.buffer.options['buftype'] = 'nofile'
        vim.current.buffer.options['modifiable'] = True
        vim.current.buffer.options['swapfile'] = False
        vim.current.window.options['winfixheight'] = True
        vim.current.window.options['winfixwidth'] = True
        vim.current.window.options['number'] = False
        vim.current.window.options['relativenumber'] = False
        existing_content = self._buffer.contents()
        log.Log("Setting buffer for %s: %s" % (self.name, existing_content),
                log.Logger.DEBUG)
        self._buffer = VimBuffer(vim.current.buffer)
        self._buffer.overwrite(existing_content)
        self.is_open = True
        self.creation_count += 1

        if self.creation_count == 1:
            cmd = 'autocmd Vdebug BufWinLeave %s' % self.name
            cmd += ' python3 debugger.mark_window_as_closed("%s")' % self.name
            vim.command(cmd)

        self.on_create()

    def destroy(self, wipeout=True):
        """ destroy window """
        if self._buffer is None:
            return
        self.is_open = False
        self._buffer = HiddenBuffer(self._buffer.contents())
        if wipeout and int(vim.eval('buffer_exists("%s")' % self.name)) == 1:
            vim.command('bwipeout %s' % self.name)
        self.on_destroy()

    def clean(self):
        """ clean all data in buffer """
        self._buffer.clean()

    def command(self, cmd):
        """ go to my window & execute command """
        winnr = self.getwinnr()
        if winnr != vim.current.window.number:
            vim.command(str(winnr) + 'wincmd w')
        vim.command(str(cmd))

    def accept_renderer(self, renderer):
        self.clean()
        self.write(renderer.render())


class BreakpointWindow(Window):

    name = "DebuggerBreakpoints"
    header = """===========================================================
 ID      | TYPE        | DATA
==========================================================="""

    def on_create(self):
        if self.creation_count == 1:
            self.insert(self.header, 0)
        self.command('setlocal syntax=debugger_breakpoint')

    def add_breakpoint(self, breakpoint):
        bp_str = " %-7i | %-11s | " % (breakpoint.id, breakpoint.type)
        if breakpoint.type == 'line':
            bp_str += "%s:%s" % (breakpoint.file, str(breakpoint.line))
        elif breakpoint.type == 'conditional':
            bp_str += "%s:%s when (%s)" % (
                breakpoint.file, str(breakpoint.line), breakpoint.condition)
        elif breakpoint.type == 'exception':
            bp_str += "Exception: %s" % breakpoint.exception
        elif breakpoint.type == 'call' or breakpoint.type == 'return':
            bp_str += "Function: %s" % breakpoint.function

        self.write(bp_str)

    def remove_breakpoint(self, breakpoint_id):
        i = 0
        for l in self._buffer.contents():
            bp_str = " %i " % breakpoint_id
            bp_id_len = len(bp_str)
            if l[:bp_id_len] == bp_str:
                self._buffer.delete(i)
            i += 1


class LogWindow(Window):

    name = "DebuggerLog"

    def on_create(self):
        self.command('setlocal syntax=debugger_log')
        if self.creation_count == 1:
            cmd = 'autocmd Vdebug BufWinLeave %s silent! bdelete %s' \
                % (self.name, self.name)
            vim.command(
                '%s | python3 vdebug.log.Log.remove_logger("WindowLogger")'
                % cmd)

    def write(self, msg, return_focus=True):
        Window.write(self, msg, return_focus=True)


class StackWindow(Window):

    name = "DebuggerStack"

    def on_create(self):
        self.command('inoremap <buffer> <cr> <esc>'
                     ':python3 debugger.handle_return_keypress()<cr>')
        self.command('nnoremap <buffer> <cr> '
                     ':python3 debugger.handle_return_keypress()<cr>')
        self.command('nnoremap <buffer> <2-LeftMouse> '
                     ':python3 debugger.handle_double_click()<cr>')
        self.command('setlocal syntax=debugger_stack')

    def write(self, msg, return_focus=True):
        Window.write(self, msg, after="normal gg")


class WatchWindow(Window):

    name = "DebuggerWatch"

    def __init__(self):
        Window.__init__(self)
        self._eval_expression = None

    def on_create(self):
        self.command('inoremap <buffer> <cr> <esc>'
                     ':python3 debugger.handle_return_keypress()<cr>')
        self.command('nnoremap <buffer> <cr> '
                     ':python3 debugger.handle_return_keypress()<cr>')
        self.command('nnoremap <buffer> <2-LeftMouse> '
                     ':python3 debugger.handle_double_click()<cr>')
        self.command('setlocal syntax=debugger_watch')

    def set_eval_expression(self, eval_expression):
        self._eval_expression = eval_expression

    def has_persistent_eval(self):
        if self.is_open:
            return self._eval_expression is not None

    def get_eval_expression(self):
        return self._eval_expression

    def clear_eval_expression(self):
        self._eval_expression = None

    def write(self, msg, return_focus=True):
        Window.write(self, msg, after="normal gg")


class StatusWindow(Window):

    name = "DebuggerStatus"

    def on_create(self):
        self.command('setlocal syntax=debugger_status')
        if self._buffer.is_empty():
            keys = util.Keymapper()
            if opts.Options.get("simplified_status", int):
                self.set_status("listening")
            else:
                output = "Status: starting\nListening on port\nNot connected\n\n"
                output += "Press %s to start debugging, " % (keys.run_key())
                output += "%s to stop/close. " % (keys.close_key())
                output += "Type :help Vdebug for more information."
                self.write(output)
                self.set_height(6)

    def set_status(self, status):
        if opts.Options.get("simplified_status", int):
            if str(status) == "listening":
                status = "●"
            if str(status) == "stopped":
                status = "■"
            if str(status) == "running":
                status = "▶"
            if str(status) == "break":
                status = "▌▌"

            keys = util.Keymapper()

            output = " " + str(status) + " "
            output += "[%s Start] " % (keys.run_key())
            output += "[%s Stop] " % (keys.close_key())
            output += "[:help Vdebug]"

            self.insert(output, 0, True)
        else:
            self.insert("Status: %s" % str(status), 0, True)

    def mark_as_stopped(self):
        self.set_status("stopped")
        if opts.Options.get("simplified_status", int) != 1:
            self.insert("Not connected", 2, True)

    def set_conn_details(self, addr, port):
        if opts.Options.get("simplified_status", int) != 1:
            self.insert("Connected to %s:%s" % (addr, port), 2, True)

    def set_listener_details(self, addr, port, idekey):
        if opts.Options.get("simplified_status", int) != 1:
            details = "Listening on %s:%s" % (addr, port)
            if idekey:
                details += " (IDE key: %s)" % idekey
            self.insert(details, 1, True)


class TraceWindow(WatchWindow):

    name = "DebuggerTrace"

    def __init__(self):
        WatchWindow.__init__(self)
        self._trace_expression = None
        self._last_context_rendered = None

    def on_create(self):
        if self.creation_count == 1:
            cmd = 'autocmd Vdebug BufWinLeave %s silent! bdelete %s' \
                % (self.name, self.name)
            vim.command(
                '%s | python3 debugger.runner.ui.tracewin.is_open = False'
                % cmd)
        self.command('setlocal syntax=debugger_watch')

    def set_trace_expression(self, trace_expression):
        self._trace_expression = trace_expression

    def is_tracing(self):
        if self.is_open:
            return self._trace_expression is not None

    def get_trace_expression(self):
        return self._trace_expression

    def render(self, renderer):
        self._last_context_rendered = renderer
        self.accept_renderer(renderer)

    def render_in_error_case(self):
        if self._last_context_rendered is None:
            self.write(str(self._trace_expression))
        else:
            self.write('(prev)' + str(self._last_context_rendered))

    def on_destroy(self):
        self._trace_expression = None
        self._last_context_rendered = None


class ResponseRenderer:

    def __init__(self, response):
        self.response = response

    def render(self):
        pass


class StackGetResponseRenderer(ResponseRenderer):

    def render(self):
        stack = self.response.get_stack()
        string = ""
        for s in stack:
            if s.get('where'):
                where = s.get('where')
            else:
                where = 'main'
            file = util.FilePath(s.get('filename'))
            line = "[%(num)s] %(where)s @ %(file)s:%(line)s" % {
                'num': s.get('level'), 'where': where,
                'file': str(file.as_local()), 'line': s.get('lineno')}
            string += line + "\n"
        return string


class ContextGetResponseRenderer(ResponseRenderer):

    def __init__(self, response, title=None, contexts=None, current_context=0):
        ResponseRenderer.__init__(self, response)
        self.title = title
        self.contexts = contexts if contexts is not None else {}
        self.current_context = current_context

    def render(self, indent=0):
        res = self.__create_tabs()

        if self.title:
            res += "- %s\n\n" % self.title

        properties = self.response.get_context()
        num_props = len(properties)
        log.Log("Writing %i properties to the window" % num_props,
                log.Logger.INFO)
        for idx, prop in enumerate(properties):
            final = False
            try:
                next_prop = properties[idx+1]
            except IndexError:
                final = True
                next_prop = None
            res += self.__render_property(prop, next_prop, final, indent)

        log.Log("Writing to window:\n"+res, log.Logger.DEBUG)

        return res

    def __create_tabs(self):
        res = []
        if self.contexts:
            for id, name in self.contexts.items():
                if self.current_context == id:
                    name = "*"+name
                res.append("[ %s ]" % name)
        if res:
            return " ".join(res) + "\n\n"
        return ""

    def __render_property(self, p, next_p, last=False, indent=0):
        indent_str = "".rjust((p.depth * 2)+indent)
        line = "%(indent)s %(marker)s %(name)s = (%(type)s)%(value)s" % {
            'indent': indent_str,
            'marker': self.__get_marker(p),
            'name': p.display_name,
            'type': p.type_and_size(),
            'value': " " + p.value
        }
        line = line.rstrip() + "\n"

        if opts.Options.get('watch_window_style') == 'expanded':
            depth = p.depth
            if next_p and not last:
                next_depth = next_p.depth
                if depth == next_depth:
                    next_sep = "|"
                    num_spaces = depth * 2
                elif depth > next_depth:
                    if not p.is_last_child:
                        line += "".rjust(depth * 2 + indent) + " |\n"
                        line += "".rjust(depth * 2 + indent) + " ...\n"
                    next_sep = "/"
                    num_spaces = (depth * 2) - 1
                else:
                    next_sep = "\\"
                    num_spaces = (depth * 2) + 1

                line += "".rjust(num_spaces+indent) + " " + next_sep + "\n"
            elif depth > 0:
                if not p.is_last_child:
                    line += "".rjust(depth * 2 + indent) + " |\n"
                    line += "".rjust(depth * 2 + indent) + " ...\n"
                line += "".rjust((depth * 2) - 1 + indent) + " /" + "\n"
        return line

    def __get_marker(self, property):
        char = opts.Options.get('marker_default')
        if property.has_children:
            if property.child_count() == 0:
                char = opts.Options.get('marker_closed_tree')
            else:
                char = opts.Options.get('marker_open_tree')
        return char
