import vdebug.opts
import vdebug.log
import vim
import re
import os
import urllib

class Keymapper:
    """Map and unmap key commands for the Vim user interface.
    """

    exclude = ["run","set_breakpoint","eval_visual"]

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
        if filename.startswith('file://'):
            filename = filename[7:]

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
        if ret[2] == "\\":
            ret = ret.replace("\\","/")

        if vdebug.opts.Options.isset('path_maps'):
            for remote, local in vdebug.opts.Options.get('path_maps', dict).items():
                if local in ret:
                    vdebug.log.Log("Replacing local path (%s) " % local +\
                            "with remote path (%s)" % remote ,\
                            vdebug.log.Logger.DEBUG)
                    ret = ret.replace(local,remote)
                    break
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
