import sys
import os
import inspect

directory = os.path.dirname(inspect.getfile(inspect.currentframe()))
sys.path.append(directory)

import vdebug.debugger_interface
