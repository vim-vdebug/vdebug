import os
import re
import socket
import sys
import time
import traceback
import urllib.parse as urllib

import vim

from . import dbgp
from . import error
from . import log
from . import opts


class ExceptionHandler:

    """ Exception handlers """

    def __init__(self, session_handler):
        self._session_handler = session_handler
        self.readable_errors = (error.EventError, error.BreakpointError,
                                error.LogError, error.NoConnectionError,
                                error.ModifiedBufferError)

    def exception_to_string(self, e):
        if isinstance(e, self.readable_errors):
            return str(e)
        return str(sys.exc_info()[0])

    def handle_timeout(self):
        """Handle a timeout, which is pretty normal.
        """
        self._session_handler.stop()
        self._session_handler.ui().say("No connection was made")

    def handle_interrupt(self):
        """Handle a user interrupt, which is pretty normal.
        """
        self._session_handler.stop()
        self._session_handler.ui().say("Connection cancelled")

    def handle_socket_end(self):
        """Handle a socket closing, which is pretty normal.
        """
        self._session_handler.ui().say(
            "Connection to the debugger has been closed"
        )
        self._session_handler.stop()

    def handle_vim_error(self, e):
        """Handle a VIM error.

        This should NOT occur under normal circumstances.
        """
        self._session_handler.ui().error("A Vim error occured: %s\n%s" %
                                         (e, traceback.format_exc()))

    def handle_readable_error(self, e):
        """Simply print an error, since it is human readable enough.
        """
        self._session_handler.ui().error(str(e))

    def handle_dbgp_error(self, e):
        """Simply print an error, since it is human readable enough.
        """
        self._session_handler.ui().error(str(e.args[0]))

    def handle_general_exception(self):
        """Handle an unknown error of any kind.
        """
        self._session_handler.ui().error("An error occured: %s\n%s" % (
            sys.exc_info()[0], traceback.format_exc(5)))

    def handle(self, e):
        """Switch on the exception type to work out how to handle it.
        """
        if isinstance(e, dbgp.TimeoutError):
            self.handle_timeout()
        elif isinstance(e, error.UserInterrupt):
            try:
                self.handle_interrupt()
            except Exception as e:
                pass
        elif isinstance(e, self.readable_errors):
            self.handle_readable_error(e)
        elif isinstance(e, dbgp.DBGPError):
            self.handle_dbgp_error(e)
        elif isinstance(e, (EOFError, socket.error)):
            self.handle_socket_end()
        elif isinstance(e, KeyboardInterrupt):
            print("Keyboard interrupt - debugging session cancelled")
            try:
                self._session_handler.stop()
            except Exception as e:
                pass
        else:
            self.handle_general_exception()


class Keymapper:

    """Map and unmap key commands for the Vim user interface.
    """

    exclude = ["run", "close", "set_breakpoint", "enable_breakpoint", "disable_breakpoint",
               "toggle_breakpoint" "eval_visual"]

    def __init__(self):
        self.is_mapped = False
        self._reload_keys()
        self.existing = []

    def run_key(self):
        return self.keymaps['run']

    def close_key(self):
        return self.keymaps['close']

    def map(self):
        log.Log("keymapper: map", log.Logger.DEBUG)
        if self.is_mapped:
            return
        self._store_old_map()
        self._reload_keys()
        for func in self.keymaps:
            if func not in self.exclude:
                key = self.keymaps[func]
                map_cmd = "noremap %s%s :python3 debugger.%s()<cr>" % (
                    self.leader, key, func)
                vim.command(map_cmd)
        self.is_mapped = True

    def reload(self):
        log.Log("keymapper: reload", log.Logger.DEBUG)
        self.is_mapped = False
        self.map()

    def _reload_keys(self):
        log.Log("keymapper: reload_keys", log.Logger.DEBUG)
        self.keymaps = vim.eval("g:vdebug_keymap")
        self.leader = vim.eval("g:vdebug_leader_key")

    def _store_old_map(self):
        log.Log("keymapper: store_old_map", log.Logger.DEBUG)
        vim.command('let tempfile=tempname()')
        tempfile = vim.eval("tempfile")
        vim.command('mkexrc! %s' % (tempfile))
        regex = re.compile(r'^([nvxsoilc]|)(nore)?map!?')
        split_regex = re.compile(r'\s+')
        keys = {v for k, v in self.keymaps.items() if k not in self.exclude}
        special = {"<buffer>", "<silent>", "<special>", "<script>", "<expr>",
                   "<unique>"}
        for line in open(tempfile, 'rb'):
            line = line.decode('utf-8', errors='replace')
            log.Log("keymapper: line '%s'" % line, log.Logger.DEBUG)
            if not regex.match(line):
                continue
            parts = split_regex.split(line)[1:]
            for p in parts:
                if p in special:
                    continue
                elif p in keys:
                    log.Log("Storing existing key mapping, '%s' " % line,
                            log.Logger.DEBUG)
                    self.existing.append(line)
                else:
                    break
        os.remove(tempfile)

    def unmap(self):
        log.Log("keymapper: unmap", log.Logger.DEBUG)
        if self.is_mapped:
            self.is_mapped = False

            for func in self.keymaps:
                key = self.keymaps[func]
                if func not in self.exclude:
                    vim.command("unmap %s%s" % (self.leader, key))
            for mapping in self.existing:
                log.Log("Remapping key with '%s' " % mapping, log.Logger.DEBUG)
                vim.command(mapping)


class FilePath:

    """Normalizes a file name and allows for remote and local path mapping.
    """

    is_win = False

    def __init__(self, filename):
        if not filename:
            raise error.FilePathError("Missing or invalid file name")
        filename = urllib.unquote(filename)
        if filename.startswith('file:'):
            filename = filename[5:]
            if filename.startswith('///'):
                filename = filename[2:]

        p = re.compile('^/?[a-zA-Z]:')
        if p.match(filename):
            self.is_win = True
            if filename[0] == "/":
                filename = filename[1:]
            filename = filename.replace('/', '\\')

        self.local = self._create_local(filename)
        self.remote = self._create_remote(filename)

    def _create_local(self, f):
        """Create the file name as a locally valid version.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f

        if opts.Options.isset('path_maps'):
            sorted_path_maps = sorted(
                opts.Options.get('path_maps', dict).items(),
                key=lambda l: len(l[0]), reverse=True)
            for remote, local in sorted_path_maps:
                if remote in ret:
                    log.Log("Replacing remote path (%s) with local path (%s)"
                            % (remote, local), log.Logger.DEBUG)
                    if not local.endswith('/') and remote.endswith('/'):
                        local = local+'/'
                    elif local.endswith('/') and not remote.endswith('/'):
                        local = local[:-1]
                    ret = ret.replace(remote, local, 1)

                    # determine remote path separator and replace by local
                    local_sep = self._findSeparator(local)
                    remote_sep = self._findSeparator(remote)
                    if local_sep and remote_sep and remote_sep != local_sep:
                        ret = ret.replace(remote_sep, local_sep)
                    break

        return ret

    @staticmethod
    def _create_remote(f):
        """Create the file name valid for the remote server.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f

        if opts.Options.isset('path_maps'):
            sorted_path_maps = sorted(
                opts.Options.get('path_maps', dict).items(),
                key=lambda l: len(l[0]), reverse=True)
            for remote, local in sorted_path_maps:
                if local in ret:
                    log.Log("Replacing local path (%s) with remote path (%s)"
                            % (local, remote), log.Logger.DEBUG)
                    if not remote.endswith('/') and local.endswith('/'):
                        remote = remote+'/'
                    elif remote.endswith('/') and not local.endswith('/'):
                        remote = remote[:-1]
                    ret = ret.replace(local, remote, 1)
                    """
                    replace remaining local separators with URL '/' separators
                    """
                    ret = ret.replace('\\', '/')
                    break

        if ret.startswith('phar://'):
            return ret
        if ret.startswith('/'):
            return "file://"+ret
        return "file:///"+ret

    def as_local(self, quote=False):
        if quote:
            return urllib.quote(self.local)
        return self.local

    def as_remote(self):
        return self.remote

    @staticmethod
    def _findSeparator(path):
        for sep in '\\/':
            if sep in path:
                return sep
        return None

    def __eq__(self, other):
        if isinstance(other, FilePath):
            if other.as_local() == self.as_local():
                return True
        return False

    def __ne__(self, other):
        if isinstance(other, FilePath):
            if other.as_local() == self.as_local():
                return False
        return True

    def __add__(self, other):
        return self.as_local() + other

    def __radd__(self, other):
        return other + self.as_local()

    def __str__(self):
        return self.as_local()

    def __repr__(self):
        return str(self)


class LocalFilePath(FilePath):

    def _create_local(self, f):
        """Create the file name as a locally valid version.

        Uses the "local_path" and "remote_path" options.
        """
        return f


class RemoteFilePath(FilePath):

    def _create_remote(self, f):
        """Create the file name valid for the remote server.

        Uses the "local_path" and "remote_path" options.
        """
        return f


class Environment:

    @staticmethod
    def reload(options=opts.Options):
        options.set(vim.eval('g:vdebug_options'))

        if options.isset('debug_file'):
            log.Log.set_logger(log.FileLogger(
                options.get('debug_file_level'), options.get('debug_file')))


class InputStream:
    """Get a character from Vim's input stream.

    Used to check for keyboard interrupts."""

    @staticmethod
    def probe():
        try:
            vim.eval("getchar(0)")
            time.sleep(0.1)
        except vim.error as e:
            raise error.UserInterrupt()
