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
        if vdebug.opts.Options.isset('remote_path'):
            rp = vdebug.opts.Options.get('remote_path')
            lp = vdebug.opts.Options.get('local_path')
            vdebug.log.Log("Replacing remote path (%s) " % rp +\
                    "with local path (%s)" % lp,\
                    vdebug.log.Logger.DEBUG)
            if ret.startswith(rp):
                ret = ret.replace(rp,lp)
        return ret

    def _create_remote(self,f):
        """Create the file name valid for the remote server.

        Uses the "local_path" and "remote_path" options.
        """
        ret = f
        if vdebug.opts.Options.isset('remote_path'):
            rp = vdebug.opts.Options.get('remote_path')
            lp = vdebug.opts.Options.get('local_path')
            vdebug.log.Log("Replacing local path (%s) " % rp +\
                    "with remote path (%s)" % lp,\
                    vdebug.log.Logger.DEBUG)
            if ret.startswith(lp):
                ret = ret.replace(lp,rp)
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
