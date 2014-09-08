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
import sys
from dbgp.common import *
import dbgp.common
dbgp.common.__builtins__['DBGPHideChildren'] = 0

# Some state constants to work around 2 limitations in pdb:
# * When at the bottom frame, all operations act like "step in"
# * Starting a debug session always stops at the first line in
#    the program - there is no way to start "running" so the first
#    stop is at the first breakpoint.
BOTFRAME_STEP = 0 # When next at the bottom frame, we will break
BOTFRAME_CONTINUE = 1 # When next at the bottom frame, we just ignore it.

ignoreModules = []
debugAll = 0
breakpointList = {}
breakpointsByFile = {}
canonicCache = {}

def setlocal(frame, varname, value):
    # locals are readonly from python, so nothing we can do here!
    sys.stderr.write("Locals are readonly, unable to set value\n")

class clientBase:
    def __init__(self):
        self.interrupt = 0
        # Default is to step at the bottom frame.
        self.botframeBehaviour = BOTFRAME_STEP
        # 2.3 or higher changed how the debugger works slightly
        self.breakOnFirstCall = not (sys.hexversion < 0x020300F0)
        self.reset()
    
    def trace_skip(self, frame):
        if not frame or not frame.f_globals or \
            frame.f_lineno == 0 or \
            frame.f_globals.has_key('DBGPHide') or \
           (frame.f_globals.has_key('__name__') and \
            ignoreModules and \
            frame.f_globals['__name__'] in ignoreModules):
            return 1
        
        # XXX bug 35933 and bug 44620
        # If this is not present, you end up having to
        # step a dozen or so times on a single print statment
        # the old way of doing this (fixed bug 35993) was extremely slow,
        # this method seems to make little or no difference in performance
        f = frame
        while f and f.f_back:
            if f.f_builtins.has_key('DBGPHideChildren'):
                return f.f_builtins['DBGPHideChildren']
            f = f.f_back
        return 0

    def trace_dispatch(self, frame, event, arg):
        # if our parent tells us to hide, carry that into our globals as well.
        # this helps perf in trace_skip somewhat
        if frame and frame.f_back and frame.f_back.f_builtins.has_key('DBGPHideChildren'):
            frame.f_builtins['DBGPHideChildren'] = frame.f_back.f_builtins['DBGPHideChildren']
        
        if self.trace_skip(frame):
            return self.trace_dispatch
        # see if we're getting a break or something
        #log.debug("trace_dispatch event=%r", event)

        # if there are commands waiting to be handled.
        # handle those commands first
        if self.interrupt:
            self.interaction(frame,None,1)
            return self.trace_dispatch
        
        try:
            if self.quitting:
                return # None
            if event == 'line':
                return self.dispatch_line(frame, arg)
            if event == 'call':
                # python 2.3 starts with call on line 1, rather than a line
                # event for line zero like earlier versions, so we need to
                # handle that and make sure we break if necessary
                if self.breakOnFirstCall:
                    self.breakOnFirstCall = 0
                    self.dispatch_call(frame, arg)
                    return self.dispatch_line(frame, arg)
                return self.dispatch_call(frame, arg)
            if event == 'return':
                return self.dispatch_return(frame, arg)
            if event == 'exception':
                return self.dispatch_exception(frame, arg)
            return self.trace_dispatch
        except DBGPQuit, e:
            # debugging has stopped with the stop command.  This does
            # not end the application, it detaches from debugging.
            # kill will end the application
            
            # dont start debugging any new threads
            set_thread_support(0)
            
            return None

    def starttrace(self):
        sys.settrace(self.trace_dispatch)

    def stoptrace(self):
        sys.settrace(None)

    def dispatch_line(self, frame, arg):
        # if we need to break or stop on this line, then do it
        if self.stop_here(frame) or self.break_here(frame):
            self.dispatch_interaction(frame)
            if self.quitting: raise DBGPQuit
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        # if we need to break or stop when making this
        # function call, do it now
        if self.botframe is None:
            # First call of dispatch since reset()
            self.botframe = frame.f_back # (CT) Note that this may also be None!
            return self.trace_dispatch
        if self.stop_here(frame) or \
           self.break_here(frame, arg, 'call'):
            self.dispatch_interaction(frame, arg)
            if self.quitting: raise DBGPQuit
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        # if we need to break or stop when returning from this
        # function call, do it now
        if self.stop_here(frame) or frame == self.returnframe or \
           self.break_here(frame, arg, 'return'):
            self.dispatch_interaction(frame, arg)
            if self.quitting: raise DBGPQuit
        return self.trace_dispatch

    def dispatch_exception(self, frame, arg):
        # if we need to break or stop on an exception, do it now
        if self.stop_here(frame) or self.break_here(frame, arg, 'exception'):
            self.dispatch_interaction(frame, arg)
            if self.quitting: raise DBGPQuit
        return self.trace_dispatch

    def stop_here(self, frame):
        # (CT) stopframe may now also be None, see dispatch_call.
        # (CT) the former test for None is therefore removed from here.
        if frame is self.stopframe:
            return 1
        while frame is not None and frame is not self.stopframe:
            if frame is self.botframe:
                return self.botframeBehaviour == BOTFRAME_STEP
            frame = frame.f_back
        return 0

    def break_here(self, frame, arg = None, type = None):
        # flag says ok to delete temp. bp
        from dbgp.client import effective
        (bp, flag) = effective(frame, arg, type)

        if bp:
            if (flag and bp.temporary):
                bp.deleteMe()
            return 1
        else:
            return 0
    
