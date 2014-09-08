#!/usr/bin/env python
# Copyright (c) 2003-2006 ActiveState Software Inc.
#
# The MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is furnished
# to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#
# Authors:
#    Shane Caraveo <ShaneC@ActiveState.com>
#    Trent Mick <TrentM@ActiveState.com>

import sys, os
try:
    import logging
except ImportError:
    from dbgp import _logging as logging

# insert a frame flag for ourselves.  This flag is used to drop frames from
# the stack that we wouldn't want to normally see.  See
# dbgpClient.get_stack
DBGPHide = 1

# Note: this is part of the dbgp API, but dbgp itself never changes it.
DBGPFullTraceback = 0

# hide children gets set when writing stdout.  This prevents deeper stack levels
# that stdout uses from showing up in the stack frame and causing breaks in weird
# places
# Importers need to add DBGPHideChildren as a builtin, set to 0
# See bug 64497

# if set allows stepping into parts of this file.
#  0 - dont allow (default)
#  1 - allow, but not the io streams
#  2 - allow plus the io streams
# constant names
DBGP_STOPPABLE_NEVER = 0
DBGP_STOPPABLE_SKIP_IO = 1
DBGP_STOPPABLE_ALWAYS = 2

DBGPDebugDebugger = DBGP_STOPPABLE_NEVER
# error codes
ERROR_OK                        = 0
ERROR_COMMAND_PARSE             = 1
ERROR_DUPLICATE_ARGS            = 2
ERROR_INVALID_ARGS              = 3
ERROR_COMMAND_NOT_SUPPORTED     = 4
ERROR_COMMAND_NOT_AVAILABLE     = 5
ERROR_FILE_ACCESS               = 100
ERROR_STREAM_REDIRECT_FAILED    = 101
ERROR_BREAKPOINT_INVALID        = 200
ERROR_BREAKPOINT_TYPE           = 201
ERROR_BREAKPOINT_INVALID_LINE   = 202
ERROR_BREAKPOINT_NOT_REACHABLE  = 203
ERROR_BREAKPOINT_STATE          = 204
ERROR_BREAKPOINT_DOES_NOT_EXIST = 205
ERROR_EVAL_FAILED               = 206
ERROR_INVALID_EXPRESSION        = 207
ERROR_PROPERTY_DOES_NOT_EXIST   = 300
ERROR_STACK_DEPTH               = 301
ERROR_CONTEXT_INVALID           = 302
ERROR_ENCODING                  = 900
ERROR_EXCEPTION                 = 998
ERROR_UNKNOWN                   = 999


DBGP_VERSION = '1.0'

MAX_CHILDREN = 10
MAX_DATA     = 256
MAX_DEPTH    = 1
SHOW_HIDDEN  = 0


# status types
STATUS_STARTING    = 0
STATUS_STOPPING    = 1
STATUS_STOPPED     = 2
STATUS_RUNNING     = 3
STATUS_BREAK       = 4
STATUS_INTERACTIVE = 5

status_names = ['starting', 'stopping', 'stopped', 'running', 'break', 'interactive']

# status reason types
REASON_OK        = 0
REASON_ERROR     = 1
REASON_ABORTED   = 2
REASON_EXCEPTION = 3

reason_names = ['ok' , 'error', 'aborted', 'exception']

RESUME_STOP = 0 # session terminated.
RESUME_STEP_IN = 1 # step into things.
RESUME_STEP_OVER = 2 # step over current thing
RESUME_STEP_OUT = 3 # step out of current thing.
RESUME_GO = 4 # go for it.
RESUME_INTERACTIVE = 5 # go for it.

resume_command_names = ['stop', 'step_into', 'step_over', 'step_out', 'run', 'interact']

def getenv(key, default=None):
    try:
        if not hasattr(os, 'getenv'):
            # on Symbian, getenv doesn't exist! (AttributeError)
            return default
        retval = os.getenv(key)
        if retval is None:
            return default
    except KeyError:
        # on Jython, one gets an exception instead of None back
        return default
    return retval

class DBGPError(Exception):
    pass

class DBGPQuit(Exception):
    """DBGPQuit
    
    an exception thrown to quit debugging
    """

__log_configured = 0
def configureLogging(log, level = logging.INFO):
    global __log_configured
    if __log_configured:
        return
    __log_configured = 1
    
    class DBGPFormatter(logging.Formatter):
        """Logging formatter to prefix log level name to all log output
        *except* normal INFO level logs.
        """
        def format(self, record):
            s = logging.Formatter.format(self, record)
            #if record.levelno != logging.INFO:
            s = "%s: %s: %s" % (record.levelname, record.name, s)
            return s

    hdlr = logging.StreamHandler()
    fmtr = DBGPFormatter()
    hdlr.setFormatter(fmtr)
    log.addHandler(hdlr)
    log.setLevel(level)
