import vdebug.opts
import vdebug.log
import vim

class Environment:
    @staticmethod
    def reload():
        vdebug.opts.Options.set(vim.eval('g:vdebug_options'))

        if vdebug.opts.Options.isset('debug_file'):
            vdebug.log.Log.set_logger(vdebug.log.FileLogger(\
                    vdebug.opts.Options.get('debug_file_level'),\
                    vdebug.opts.Options.get('debug_file')))
