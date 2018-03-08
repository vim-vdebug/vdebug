import inspect
import os
import sys

directory = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(directory)

import vdebug.debugger_interface
