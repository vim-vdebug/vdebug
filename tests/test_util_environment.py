if __name__ == "__main__":
    import sys
    sys.path.append('../plugin/python/')
import unittest2 as unittest
""" Mock vim import """
import vdebug.log
import vim
from mock import MagicMock, patch
from vdebug.util import Environment

class EnvironmentTest(unittest.TestCase):
    def test_reload_evals_options(self):
        new_options = {"foo":"bar"}
        options = MagicMock()
        options.isset = MagicMock(return_value=False)
        vim.eval = MagicMock(return_value=new_options)

        vdebug.util.Environment.reload(options)

        vim.eval.assert_called_once_with("g:vdebug_options")
        options.set.assert_called_once_with(new_options)
