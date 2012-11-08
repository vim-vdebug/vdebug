import vdebug.opts
import vdebug.log
import vim
import sys

class Keymapper:
    """Map and unmap key commands for the Vim user interface.
    """

    exclude = ["run","set_breakpoint"]

    def __init__(self):
        self.keymaps = vim.eval("g:vdebug_keymap")
        self.leader = vim.eval("g:vdebug_leader_key")
        self.is_mapped = False

    def map(self):
        if self.is_mapped:
            return
        for func in self.keymaps:
            key = self.keymaps[func]
            if func not in self.exclude:
                map_cmd = "map %s%s :python debugger.%s()<cr>" %\
                    (self.leader,key,func)
                vim.command(map_cmd)
        self.is_mapped = True

    def unmap(self):
        if self.is_mapped:
            self.is_mapped = False

            for func in self.keymaps:
                key = self.keymaps[func]
                if func not in self.exclude:
                    vim.command("unmap %s%s" %(self.leader,key))

class FilePath:
    """Normalizes a file name and allows for remote and local path mapping.
    """
    def __init__(self,filename):
        if filename is None or \
            len(filename) == 0:
            raise FilePathError, "Missing or invalid file name"
        if filename.startswith('file:///'):
            if sys.platform == "win32":
                """ remove prefix till the drive letter """
                filename = filename[8:]
            else:
                filename = filename[7:]
        self.local = self._create_local(filename)
        self.remote = self._create_remote(filename)

    def _create_local(self,f):
        """Create the file name as a locally valid version.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f
        if vdebug.opts.Options.isset('path_maps'):
            for remote, local in vdebug.opts.Options.get('path_maps', dict).items():
                if ret.startswith(remote):
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
                if ret.startswith(local):
                    vdebug.log.Log("Replacing local path (%s) " % local +\
                            "with remote path (%s)" % remote ,\
                            vdebug.log.Logger.DEBUG)
                    ret = ret.replace(local,remote)
                    break
        return ret

    def as_local(self):
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

class FilePathError(Exception):
    pass

class InputStream:
    """Get a character from Vim's input stream.

    Used to check for keyboard interrupts."""

    def probe(self):
        try:
            vim.eval("getchar(0)")
        except vim.error:
            raise UserInterrupt

class UserInterrupt(Exception):
    """Raised when a user interrupts connection wait."""
