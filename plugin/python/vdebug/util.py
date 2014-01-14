import vdebug.opts
import vdebug.log
import vdebug.session
import vdebug.breakpoint
import vim
import re
import os
import sys
import traceback
import socket
import urllib

class ExceptionHandler:
    def __init__(self, session):
        self._session = session
        self.readable_errors = (vdebug.event.EventError,
                vdebug.breakpoint.BreakpointError,
                vdebug.log.LogError,
                vdebug.session.NoConnectionError,
                vdebug.session.ModifiedBufferError)


    """ Exception handlers """

    def handle_timeout(self):
        """Handle a timeout, which is pretty normal. 
        """
        self._session.close()
        self._session.ui().say("No connection was made")

    def handle_interrupt(self):
        """Handle a user interrupt, which is pretty normal. 
        """
        self._session.close()
        self._session.ui().say("Connection cancelled")

    def handle_socket_end(self):
        """Handle a socket closing, which is pretty normal.
        """
        self._session.ui().say("Connection to the debugger has been closed")
        self._session.close_connection()

    def handle_vim_error(self,e):
        """Handle a VIM error.

        This should NOT occur under normal circumstances.
        """
        self._session.ui().error("A Vim error occured: %s\n%s"\
                        % (str(e), traceback.format_exc()))

    def handle_readable_error(self,e):
        """Simply print an error, since it is human readable enough.
        """
        self._session.ui().error(str(e))

    def handle_dbgp_error(self,e):
        """Simply print an error, since it is human readable enough.
        """
        self._session.ui().error(str(e.args[0]))

    def handle_general_exception(self):
        """Handle an unknown error of any kind.
        """
        self._session.ui().error("An error occured: %s\n%s"\
                        % (str(sys.exc_info()[0]), traceback.format_exc()))

    def handle(self, e):
        """Switch on the exception type to work out how to handle it.
        """
        if isinstance(e, vdebug.dbgp.TimeoutError):
            self.handle_timeout()
        elif isinstance(e, vdebug.util.UserInterrupt):
            try:
                self.handle_interrupt()
            except:
                pass
        elif isinstance(e, self.readable_errors):
            self.handle_readable_error(e)
        elif isinstance(e, vdebug.dbgp.DBGPError):
            self.handle_dbgp_error(e)
        elif isinstance(e, (EOFError,socket.error)):
            self.handle_socket_end()
        elif isinstance(e, KeyboardInterrupt):
            print "Keyboard interrupt - debugging session cancelled"
            try:
                self._session.close()
            except:
                pass
        else:
            self.handle_general_exception()
        """
        elif isinstance(e,vim.error):
            self.handle_vim_error(e)
        """

class Keymapper:
    """Map and unmap key commands for the Vim user interface.
    """

    exclude = ["run", "close", "set_breakpoint", "eval_visual"]

    def __init__(self):
        self.keymaps = vim.eval("g:vdebug_keymap")
        self.leader = vim.eval("g:vdebug_leader_key")
        self.is_mapped = False
        self.existing = []

    def run_key(self):
        return self.keymaps['run']

    def close_key(self):
        return self.keymaps['close']

    def map(self):
        if self.is_mapped:
            return
        self._store_old_map()
        for func in self.keymaps:
            if func not in self.exclude:
                key = self.keymaps[func]
                map_cmd = "noremap %s%s :python debugger.%s()<cr>" %\
                    (self.leader,key,func)
                vim.command(map_cmd)
        self.is_mapped = True

    def _store_old_map(self):
        vim.command('let tempfile=tempname()')
        tempfile = vim.eval("tempfile")
        vim.command('mkexrc! %s' % (tempfile))
        regex = re.compile(r'^([nvxsoilc]|)(nore)?map!?')
        split_regex = re.compile(r'\s+')
        keys = set(v for (k,v) in self.keymaps.items() if k not in self.exclude)
        special = set(["<buffer>", "<silent>", "<special>", "<script>", "<expr>", "<unique>"])
        for line in open(tempfile, 'r'):
            if not regex.match(line):
                continue
            parts = split_regex.split(line)[1:]
            for p in parts:
                if p in special:
                    continue
                elif p in keys:
                    vdebug.log.Log("Storing existing key mapping, '%s' " % line,
                                   vdebug.log.Logger.DEBUG)
                    self.existing.append(line)
                else:
                    break
        os.remove(tempfile)

    def unmap(self):
        if self.is_mapped:
            self.is_mapped = False

            for func in self.keymaps:
                key = self.keymaps[func]
                if func not in self.exclude:
                    vim.command("unmap %s%s" %(self.leader,key))
            for mapping in self.existing:
                vdebug.log.Log("Remapping key with '%s' " % mapping,\
                        vdebug.log.Logger.DEBUG)
                vim.command(mapping)

class FilePath:
    is_win = False

    """Normalizes a file name and allows for remote and local path mapping.
    """
    def __init__(self,filename):
        if filename is None or \
            len(filename) == 0:
            raise FilePathError("Missing or invalid file name")
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

        self.local = self._create_local(filename)
        self.remote = self._create_remote(filename)

    def _create_local(self,f):
        """Create the file name as a locally valid version.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f
        if ret[2] == "/":
            ret = ret.replace("/","\\")

        if vdebug.opts.Options.isset('path_maps'):
            for remote, local in vdebug.opts.Options.get('path_maps', dict).items():
                if remote in ret:
                    vdebug.log.Log("Replacing remote path (%s) " % remote +\
                            "with local path (%s)" % local ,\
                            vdebug.log.Logger.DEBUG)
                    ret = ret.replace(remote,local)
                    break
        return ret

    def _create_remote(self,f):
        """Create the file name valid for the remote server.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f

        if vdebug.opts.Options.isset('path_maps'):
            for remote, local in vdebug.opts.Options.get('path_maps', dict).items():
                if local in ret:
                    vdebug.log.Log("Replacing local path (%s) " % local +\
                            "with remote path (%s)" % remote ,\
                            vdebug.log.Logger.DEBUG)
                    ret = ret.replace(local,remote)
                    break

        if ret[2] == "\\":
            ret = ret.replace("\\","/")

        if self.is_win:
            return "file:///"+ret
        else:
            return "file://"+ret

    def as_local(self,quote = False):
        if quote:
            return urllib.quote(self.local)
        else:
            return self.local

    def as_remote(self):
        return self.remote

    def __eq__(self,other):
        if isinstance(other,FilePath):
            if other.as_local() == self.as_local():
                return True
        return False

    def __ne__(self,other):
        if isinstance(other,FilePath):
            if other.as_local() == self.as_local():
                return False
        return True

    def __add__(self,other):
        return self.as_local() + other

    def __radd__(self,other):
        return other + self.as_local()

    def __str__(self):
        return self.as_local()

    def __repr__(self):
        return str(self)

class LocalFilePath(FilePath):
    def _create_local(self,f):
        """Create the file name as a locally valid version.

        Uses the "local_path" and "remote_path" options.
        """
        return f

class RemoteFilePath(FilePath):
    def _create_remote(self,f):
        """Create the file name valid for the remote server.

        Uses the "local_path" and "remote_path" options.
        """
        return f

class Environment:
    @staticmethod
    def reload():
        vdebug.opts.Options.set(vim.eval('g:vdebug_options'))

        if vdebug.opts.Options.isset('debug_file'):
            vdebug.log.Log.set_logger(vdebug.log.FileLogger(\
                    vdebug.opts.Options.get('debug_file_level'),\
                    vdebug.opts.Options.get('debug_file')))

class FilePathError(Exception):
    pass

class InputStream:
    """Get a character from Vim's input stream.

    Used to check for keyboard interrupts."""

    def probe(self):
        try:
            vim.eval("getchar(0)")
        except: # vim.error
            raise UserInterrupt()

class UserInterrupt(Exception):
    """Raised when a user interrupts connection wait."""
