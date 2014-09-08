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
if sys.hexversion < 0x020000F0:
    exe = sys.executable
    ver = '.'.join(map(str, sys.version_info[:3]))
    sys.stderr.write("The dbgpClient must be run with Python "
                     "version 2.0 or greater. Your current "
                     "python, '%s', is version '%s'\n"
                     % (exe, ver))
    sys.exit(1)

import socket, copy
import thread, threading
import tokenize
# command line host driver
import getopt, os, types, StringIO, Queue
import traceback, re
import base64, urlparse
import dbgp.listcmd as listcmd

from dbgp.common import *
import dbgp.common
dbgp.common.__builtins__['DBGPHideChildren'] = 0

try:
    import logging
except ImportError:
    from dbgp import _logging as logging

log = logging.getLogger("dbgp.client")

# Import the client support module (implemented in C for some Python
# versions for speed).
if sys.hexversion < 0x02020000:
    # We don't compile _clientXY for pre-2.2 Python.
    from dbgp._pyclient import *
else:
    major = sys.hexversion >> 24
    minor = (sys.hexversion & 0x00ff0000) >> 16
    modname = "_client%s%s" % (major, minor)
    try:
        # Try importing our fast C module.
        import imp
        import dbgp
        info = imp.find_module(modname, dbgp.__path__)
        _client = imp.load_module(modname, *info)
        sys.modules["_client"] = _client
        from _client import *
        del sys.modules["_client"], info, _client
    except ImportError, ex:
        #configureLogging(log, logging.INFO)
        #log.exception(ex)
        # Fallback to pure Python support module.
        from dbgp._pyclient import *
    del major, minor, modname


# prevent internal DBGP threads from getting debugged.  Any thread started
# from DBGP for debugger purposes should use _nonDebugThread
# to start threads with.
_nonDebugThread = thread.start_new_thread

# base types do not have children
BaseTypes = [types.StringType,
             types.UnicodeType,
             types.IntType,
             types.LongType,
             types.FloatType]

if sys.hexversion >= 0x020300F0:
    BaseTypes.append(type(True))

StringTypes = [types.StringType,
             types.UnicodeType]

HiddenTypes = [types.BuiltinMethodType,
               types.BuiltinFunctionType,
               types.FunctionType,
               types.TypeType, # py2to3 => type
               types.ModuleType]
if sys.version_info[0] >= 3:
    _is_py3 = True
    _byte0 = '\0'.encode()
    _supports_keyed_sort = True
    def _encode_response(response):
        # response is already utf-8-encoded
        return ('%d' % len(response)).encode('utf-8') + _byte0 + response + _byte0
else:
    _is_py3 = False
    #Assume version 2 -- Python 1.* not supported.
    HiddenTypes += [types.UnboundMethodType,
                    types.ClassType]
    _supports_keyed_sort = sys.version_info[1] >= 4
    def _encode_response(response):
        # response is already utf-8-encoded
        packet = '%d\0%s\0' % (len(response), response)
        return packet.encode()

if hasattr('', '__add__'):
    HiddenTypes.append(type(''.__add__))

# these are the names of the different contexts available from python, which show up
# in Komodo as variable tabs in the debugger pane.  contexts after the first are
# based the global namespace, and show specificly the variable types listed in
# the hiddenContextTypes list.  The first context is always the local context.
# the local context behaves differently than the global contexts.  It will show the
# types in the list IN ADDITION to regular variables.  The global contexts will exclude
# any type not in the list.
contextNames = ['Locals', 'Globals', 'Code Objects']
hiddenContextTypes = [[], [], HiddenTypes]

startupDir = os.getcwd()

if os.name == 'java': # for jython
    # Check if we are running a recent enough version of jython
    # Currently we have problems with v<2.1

    if not hasattr(sys, 'version_info') or int(''.join(map(str, sys.version_info[0:3]))) < 210:
        print 'Jython debugging is not support for Jython versions below 2.1'
        sys.exit(1)

    # Check if we are running on windows
    import java.lang.System
    isWindows = java.lang.System.getProperty("os.name").lower()[0:3] == 'win'
else:
    isWindows = sys.platform[0:3].lower() == 'win'

# This is needed due to http://bugs.python.org/issue6496
# Not all instances of urllib.pathname2url and urllib.url2pathname
# get converted.
if _is_py3:
    from urllib.request import pathname2url as urllib_pathname2url
    from urllib.request import url2pathname as urllib_url2pathname
else:
    from urllib import pathname2url as urllib_pathname2url
    from urllib import url2pathname as urllib_url2pathname

def url2pathname( url ):
    decomposedURL = urlparse.urlparse( url, 'file:///' )

    path = decomposedURL[2]
    # The path will begin with a superfluous '/' in this case

    if ( url.strip().lower()[0:8] == 'file:///' and isWindows):
        path = path[1:]

    if os.name == 'java' and isWindows:
        # because jython's url2path does not correctly detect the platform,
        # we need to import nturl2path explicitly
        import nturl2path
        return nturl2path.url2pathname(path)
    else:
        return urllib_url2pathname( path )

_leading_slash_re = re.compile('(/*)')
def pathname2url( pathname ):
    if os.name == 'java' and isWindows:
        # because jython's url2path does not correctly detect the platform,
        # we need to import nturl2path explicitly
        import nturl2path
        fullPath = nturl2path.pathname2url(os.path.abspath(pathname))
    else:
        fullPath = urllib_pathname2url(os.path.abspath(pathname))
    numLeadingSlashes = len(_leading_slash_re.match(fullPath).group(1))
    if numLeadingSlashes > 3:
        numLeadingSlashes = 3
    return 'file:' + '/' * (3 - numLeadingSlashes) + fullPath

# Only used by jython
def findOpenPort(start, retries):
    """findOpenPort(9000) => 9002

    Return the first open port greater or equal to the specified one."""

    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for i in range(retries):
        port = start+i
        try:
            test_socket.bind(('',port))
            return port
        except socket.error:
            pass

    raise "Could not find open port from %d to %d." % (start, start + retries)

# duplicated from xml.sax.saxutils to avoid sax requirement
def escape(data, entities={}):
    """Escape &, <, and > in a string of data.

    You can escape other strings of data by passing a dictionary as
    the optional entities parameter.  The keys and values must all be
    strings; each key will be replaced with its corresponding value.
    """
    if _is_py3 and type(data) == types.StringType:
        data = data.decode('utf-8')
    data = data.replace("&", "&amp;")
    data = data.replace("<", "&lt;")
    data = data.replace(">", "&gt;")
    for chars, entity in entities.items():
        data = data.replace(chars, entity)
    return data

# duplicated from xml.sax.saxutils to avoid sax requirement
def quoteattr(data, entities={}):
    """Escape and quote an attribute value.

    Escape &, <, and > in a string of data, then quote it for use as
    an attribute value.  The \" character will be escaped as well, if
    necessary.

    You can escape other strings of data by passing a dictionary as
    the optional entities parameter.  The keys and values must all be
    strings; each key will be replaced with its corresponding value.
    """
    if type(data) not in StringTypes:
        return '"%s"' % str(data)

    data = escape(data, entities)
    if '"' in data:
        if "'" in data:
            data = '"%s"' % data.replace('"', "&quot;")
        else:
            data = "'%s'" % data
    else:
        data = '"%s"' % data
    return data

def _getAttrStr(attrs):
    """Construct an XML-safe attribute string from the given attributes

        "attrs" is a dictionary of attributes

    The returned attribute string includes a leading space, if necessary,
    so it is safe to use the string right after a tag name.
    """
    s = ''
    for attr, value in attrs.items():
        s += ' %s=%s' % (attr, quoteattr(value))
    return s

def _filename_from_frame_py2(frame):
    if frame.f_code and frame.f_code.co_filename:
        return frame.f_code.co_filename
    return None

def _filename_from_frame_py3(frame):
    co = frame.f_code
    if not co.co_filename or co.co_filename == "<string>":
        return frame.f_globals.get('__file__', co.co_filename)
    return co.co_filename

if _is_py3:
    _filename_from_frame = _filename_from_frame_py3
else:
    _filename_from_frame = _filename_from_frame_py2

def _get_stack_data(item):
    frame, lineno = item
    where = None
    if frame.f_code.co_name == '?':
        if frame.f_locals.has_key('__name__'):
            where = frame.f_locals['__name__']
        elif frame.f_globals.has_key('__name__'):
            where = frame.f_globals['__name__']
    if not where:
        where = frame.f_code.co_name or '?'
    codeFileName = _filename_from_frame(frame)

    if codeFileName.startswith('<'):
        filename = codeFileName
        lineno = 0
    elif os.path.isfile(codeFileName):
        filename = codeFileName
    else:
        # OK, what probably happened is that the .py[c,o] file
        # was relocated and no longer points to
        # a correct source file. We will try to find the source
        # file in the same directory as the
        # .py[c,o] file.
        if not frame.f_globals.has_key('__file__'):
            # This actually seems possible based on import.c
            filename = codeFileName
        else:
            moduleFileName = frame.f_globals['__file__']
            if os.path.isabs(moduleFileName):
                filename = os.path.join(
                            os.path.dirname(moduleFileName),
                            os.path.basename(codeFileName))
            else:
                # Assume that all module imports were relative
                # the the current directory at kdb startup.
                # This should work most of the time. Heck, it
                # might not even be necessary because, due
                # to the compile, all paths seem to be absolute.
                filename = os.path.join(startupDir,
                                os.path.dirname(moduleFileName),
                                os.path.basename(codeFileName))
    return (filename, lineno, where)

def _stack_repr(stack):
    level = 0;
    for item in stack:
        level = level + 1
        (filename, lineno, where) = _get_stack_data(item)
        print "%d %s:%d:%s" % (level,filename, lineno, where)

def _hide_stack(f):
    return DBGPDebugDebugger == DBGP_STOPPABLE_NEVER and f.f_globals.has_key('DBGPHide')

def _print_tb(tb, limit=None, file=None):
    """Print up to 'limit' stack trace entries from the traceback 'tb'.

    If 'limit' is omitted or None, all entries are printed.  If 'file'
    is omitted or None, the output goes to sys.stderr; otherwise
    'file' should be an open file or file-like object with a write()
    method.
    """
    import linecache
    if not file:
        file = sys.stderr
    if limit is None:
        if hasattr(sys, 'tracebacklimit'):
            limit = sys.tracebacklimit
    n = 0
    orig_tb = tb
    while tb is not None and (limit is None or n < limit):
        if DBGPFullTraceback or not _hide_stack(tb.tb_frame):
            (filename, lineno, name) = _get_stack_data((tb.tb_frame, tb.tb_lineno))
            file.write('  File "%s", line %d, in %s\n' % (filename,lineno,name))
            line = linecache.getline(filename, lineno)
            if line: file.write('    %s\n' % line.strip())
            n = n+1
        tb = tb.tb_next
    if n < 1:
        # exception happened in dbgp, and there are no stacks for the user, lets just
        # do a regular print_tb
        traceback.print_tb(orig_tb, limit, file)

def _print_exception(etype, value, tb, limit=None, file=None):
    """Print exception up to 'limit' stack trace entries from 'tb' to 'file'.

    This differs from print_tb() in the following ways: (1) if
    traceback is not None, it prints a header "Traceback (most recent
    call last):"; (2) it prints the exception type and value after the
    stack trace; (3) if type is SyntaxError and value has the
    appropriate format, it prints the line where the syntax error
    occurred with a caret on the next line indicating the approximate
    position of the error.
    """
    if not file:
        file = sys.stderr
    if tb:
        file.write('Traceback (most recent call last):\n')
        _print_tb(tb, limit, file)
    lines = traceback.format_exception_only(etype, value)
    for line in lines[:-1]:
        file.write(line+' ')
    file.write(lines[-1])

def _print_exc(limit=None, file=None):
    """Shorthand for 'print_exception(sys.exc_type, sys.exc_value, sys.exc_traceback, limit, file)'.
    (In fact, it uses sys.exc_info() to retrieve the same information
    in a thread-safe way.)"""
    if not file:
        file = sys.stderr
    try:
        etype, value, tb = sys.exc_info()
        _print_exception(etype, value, tb, limit, file)
    finally:
        etype = value = tb = None

#py3 problems -- code doesn't contain filename...
# No one calls this function anyway...
def _code_repr(code,name=None):
    if code:
        if name is None: name = code.co_name
        if code.co_filename:
            fname = os.path.split(code.co_filename)[1]
        else:
            fname = "??"
        v = Property('code','code',code)
        v.encoding = None
        return v.toxml()
        return "Code %s: args: %r %s,%d (%r)" % (name,
                                                 code.co_varnames[:code.co_argcount],
                                                 fname,
                                                 code.co_firstlineno,
                                                 code)
    else:
        return "Code %s: None" % (name,)

def _frame_repr(frame,name=None):
    if name is None: name = ""
    if frame:
        fname = _filename_from_frame(frame)
        if fname:
            fname = os.path.split(fname)[1]
        else:
            fname = "??"
        v = Property('frame','frame',frame)
        v.encoding = None
        return v.toxml()
    else:
        return "Frame %s: None" % (name,)

def _get_object_type_string(value):
    try:
        return type(value).__name__
    except AttributeError:
        return str(type(value))

def _format_exception_only():
    try:
        # Assume exception can be formatted as a list of with single element, with a trailing \n.
        return traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])[0][:-1]
    except IndexError:
        return str(sys.exc_info()[0]) + ": " + str(sys.exc_info()[1])

def _frame_name_dump(frame):
    fname = _filename_from_frame(frame) or "??"
    if frame.f_globals.has_key('__name__'):
        return "%s at %s:%d" % (frame.f_globals['__name__'],
                                fname,
                                frame.f_lineno)
    else:
        return "?? at %s:%d" % (fname,
                                frame.f_lineno)

def _safe_apply(what_failed, func, *args):
    try:
        return apply(func, args)
    except:
        return "%s failed - %s: %s" % (what_failed, sys.exc_info()[0], sys.exc_info()[1])

def _safe_index(what_failed, ob, index):
    try:
        return ob[index]
    except:
        return "%s[%s] failed - %s: %s" % (what_failed, index, sys.exc_info()[0], sys.exc_info()[1])

classre = re.compile(r'<(?P<fullname>.*?\.(?P<name>.*?)\'?)(?:\s|>)+')
_file_obj_re = re.compile(r'<(?P<fullname>(?:open|closed)\s+file.*?)(?:,|>)')
def _class_names(ob):
    # returns a dictionary like:
    # {'fullname': 'exceptions.Exception', 'name': 'Exception'}
    try:
        m = classre.match(repr(ob))
        if m:
            return m.groupdict()
        m = _file_obj_re.match(repr(ob))
        if m:
            return m.groupdict()
        return None
    except:
        return None

# fix getopt.  we don't care if extra options are passed in, lets
# be as lenient as possible
def short_has_arg(opt, shortopts):
    for i in range(len(shortopts)):
        if opt == shortopts[i] != ':':
            return shortopts.startswith(':', i+1)
    return 0

getopt.short_has_arg = short_has_arg


# we have to execute our debugging scripts under a __main__ module.
# Unfortunately, we're already using it. So we create a fake __main__ with imp,
# and use ihooks to prevent a script for accessing the 'real' __main__. However,
# if the script imported dbgpClient.brk, then it controls main, and we don't
# want to do ihooks, so all the h_e* functions will work without our magic main
# module.

try:
    import ihooks
    Hooks = ihooks.Hooks
    _verbose = ihooks.VERBOSE
    ihooks.DBGPHide = 1
except ImportError:
    # Jython doesn't have ihooks. We put in a placeholder
    # for now.  This will limit what jython debugging can do.
    _verbose = 0
    class Hooks:
        def __init__(self, verbose = _verbose):
            self.verbose = verbose
        def modules_dict(self): return sys.modules
        pass

import imp

class h_main:
    """
    h_main creates a module that can be used for exec'ing scripts with their own
    __main__ module. This should be created seperately, and provided as a
    parameter to the h_exec* functions below
    """
    def __init__(self, main_name='__main__'):
        import __main__
        self.name = main_name
        self.module = imp.new_module(main_name)
        if hasattr(__main__, '__builtins__'): # not Jython
            self.module.__builtins__ = __main__.__builtins__
        self.locals = self.globals = self.module.__dict__

class h_base(Hooks):

    def setModule(self, module):
        d = self.modules_dict()
        if d.has_key(module.name):
            self.old_main = d[module.name]
        d[module.name] = module.module

    def resetModule(self, module):
        d = self.modules_dict()
        if self.old_main:
            d[module.name] = self.old_main

    def setSysInfo(self, mysys, file, args):
        mysys.argv = args

        if os.path.dirname(file) not in mysys.path:
            if mysys.path[0] == '':
                mysys.path.insert(1, os.path.dirname(file))
            else:
                mysys.path.insert(0, os.path.dirname(file))

class h_exec(h_base):
    """
    h_exec(code, globals, locals, module)

    This class should be called like a function and no reference to it should be
    maintained. The module parameter is a h_main instance. It emulates exec
    using a special __main__ module so that scripts depending on the use of
    __main__ will operate correctly.
    """
    def __init__(self, code, globals=None, locals=None, module=None, verbose = _verbose, tracer=None):
        h_base.__init__(self, verbose)
        if not isinstance(code, types.CodeType):
            code = code+'\n'
        if module:
            h_base.__init__(self, verbose)
            if not globals:
                globals = module.globals
            if not locals:
                locals = module.locals
            self.setModule(module)
        else:
            if not globals:
                globals = {}
            if not locals:
                locals = globals
        try:
            if tracer:
                tracer.starttrace()
            exec code in globals, locals
        finally:
            if tracer:
                tracer.stoptrace()
            if module:
                self.resetModule(module)

class h_eval(h_base):
    """
    h_eval(code, globals, locals, module)

    This class should be called like a function and no reference to it should be
    maintained. TThe module parameter is a h_main instance. It emulates eval
    using a special __main__ module so that scripts depending on the use of
    __main__ will operate correctly.
    """
    def __init__(self, code, globals=None, locals=None, module=None, verbose = _verbose, tracer=None):
        h_base.__init__(self, verbose)
        if not isinstance(code, types.CodeType):
            code = code+'\n'
        if module:
            h_base.__init__(self, verbose)
            if not globals:
                globals = module.globals
            if not locals:
                locals = module.locals
            self.setModule(module)
        else:
            if not globals:
                globals = {}
            if not locals:
                locals = globals
        try:
            if tracer:
                tracer.starttrace()
            return eval(code, globals, locals)
        finally:
            if tracer:
                tracer.stoptrace()
            if module:
                self.resetModule(module)

class h_execfile(h_base):
    """
    h_execfile(filename, args, module)

    This class should be called like a function and no reference to it should be
    maintained. The module parameter is a h_main instance. It emulates execfile
    using a special __main__ module so that scripts depending on the use of
    __main__ will operate correctly.
    """
    def __init__(self, file, args, globals=None, locals=None, module=None, verbose = _verbose, tracer=None, profiler=None):
        if module:
            h_base.__init__(self, verbose)
            d = self.modules_dict()
            self.setSysInfo(d['sys'], file, args)
            # add __file__, bug 43703
            if module.name == '__main__' and not hasattr(module.module,'__file__'):
                module.module.__file__ = file
            if not globals:
                globals = module.globals
            if not locals:
                locals = module.locals
            self.setModule(module)
        else:
            if not globals:
                globals = {}
            if not locals:
                locals = globals
            self.setSysInfo(sys, file, args)

        try:
            exec "import site\n\n" in globals, locals
            del globals['site']
            if _is_py3:
                globals['__file__'] = file
                encoding = self._get_file_encoding(file)
                fd = open(file)
                try:
                    contents = fd.read()
                finally:
                    fd.close()
                if not contents.endswith("\n"):
                    # Work around komodo bug 88566
                    # python bug http://bugs.python.org/issue10204
                    contents += "\n"
                if tracer:
                    tracer.starttrace()
                if profiler:
                    profiler.runcall(eval, compile(contents, file, 'exec'), globals, locals)
                else:
                    exec(contents, globals, locals)
            else:
                if tracer:
                    tracer.starttrace()
                if profiler:
                    profiler.runcall(execfile, file, globals, locals)
                else:
                    execfile(file, globals, locals)
        finally:
            if tracer:
                tracer.stoptrace()
            if module:
                self.resetModule(module)

    def _get_file_encoding(self, filename):
        fp = open(filename, 'rb')
        try:
            try:
                encoding, line = tokenize.detect_encoding(fp.readline)
            except SyntaxError:
                encoding = "utf-8"
        finally:
            fp.close()
        return encoding


class StreamOut:
    # this class is used for copying/redirecting the
    # stdout and stderr streams

    # XXX this may not be necessary:
    # we use cStringIO to provide the typical file functions, then on any
    # write we clear the buffer and send the entire buffer.

    def __init__(self, name, origStream, client, redirect = 0):
        self.__dict__['_name'] = name
        self.__dict__['_client'] = client
        self.__dict__['_redirect'] = redirect
        self.__dict__['_origStream'] = origStream

    def stop(self):
        return self._origStream

    def write(self, s):
        global DBGPHideChildren
        origDBGPHideChildren = DBGPHideChildren
        DBGPHideChildren = DBGPDebugDebugger != DBGP_STOPPABLE_ALWAYS
        haveBytes = type(s) != str
        try:
            if not haveBytes:
                byteString = s.encode('UTF-8')
                charString = s
            else:
                byteString = s
                if _is_py3:
                    charString = s.decode()
                else:
                    charString = s
            if not self._redirect:
                try:
                    self._origStream.write(charString)
                except Exception:
                    log.exception("Error trying to write a charString:%r to self._origStream", charString)
            try:
                self._client.send_stream(self._name, byteString)
            except Exception:
                log.exception("Error trying to write a byteString:%r to self._origStream", byteString)
        finally:
            DBGPHideChildren = origDBGPHideChildren

    def writelines(self, lines):
        text = ''.join(lines)
        self.write(text)

    def __getattr__(self, attr):
        if self.__dict__.has_key(attr):
            return getattr(self,attr)
        return getattr(self._origStream, attr)

class StreamStdin:
    # this class is used for doing a notification of stdin reads
    def __init__(self, origStream, client):
        self.__dict__['_client'] = client
        self.__dict__['_origStream'] = origStream

    def stop(self):
        return self._origStream

    def read(self, size=-1):
        self._client.notify('stdin')
        return self._origStream.read(size)

    def readline(self, size=-1):
        self._client.notify('stdin')
        return self._origStream.readline(size)

    def readlines(self, size=-1):
        self._client.notify('stdin')
        return self._origStream.readlines(size)

    def __getattr__(self, attr):
        if self.__dict__.has_key(attr):
            return getattr(self,attr)
        return getattr(self._origStream, attr)

if _is_py3:
    # io.StringIO in Python3 is so different from Python2's StringIO.StringIO
    # that it's better to clone the whole class.
    class StreamIn(io.StringIO):
        def __init__(self, origStream, client):
            io.StringIO.__init__(self, '')
            self._origStream = origStream
            self._read_cv = threading.Condition()
            self._client = client
            # io.StringIO doesn't provide buf!
            self.buf = ""

        def stop(self):
            if not self.closed:
                self.write('')
                io.StringIO.close(self)
            return self._origStream

        def _partition_data(self, data, size):
            # remove what we read from the stream
            # this ensures that reading from the beginning
            # will always give us new data, we're not in the
            # business of data storage here.
            # @param data {string} - current chars read in
            # @param size {int} - number of chars intended to read, or -1

            # assert reference(data) != reference(self.buf)
            if size == -1:
                self.buf = ''
                return data
            else:
                self.buf = data[size:]
                return data[:size]

        def write(self, s):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            self._read_cv.acquire()
            try:
                # always write to the end
                io.StringIO.seek(self, 0, os.SEEK_END)
                io.StringIO.write(self, s)
                self._read_cv.notify()
            finally:
                self._read_cv.release()

        def read(self, size = -1):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            if size is None: # Some clients can pass this in as a synonym of size=-1
                size = -1
            if self.buf and (size == -1 or len(self.buf) >= size):
                if size == -1:
                    size = len(self.buf)
                s = self.buf[:size]
                self.buf = self.buf[size:]
                return s
            self._read_cv.acquire()
            try:
                try:
                    # no buffer available, block until we have something
                    self._client.notify('stdin')
                    self._read_cv.wait()
                    # always read from the start
                    if self.closed:
                        return None
                    io.StringIO.seek(self, 0, 0)
                    data = self.buf + io.StringIO.read(self)
                    io.StringIO.seek(self, 0, 0)
                    io.StringIO.truncate(self)
                    # remove what we read from the stream
                    # this ensures that reading from the beginning
                    # will always give us new data, we're not in the
                    # business of data storage here.
                    return self._partition_data(data, size)
                except:
                    log.exception("big problemo in read")
            finally:
                self._read_cv.release()
            return x

        def readline(self, size = -1):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            if self.buf and "\n" in self.buf:
                if size == -1:
                    idx = self.buf.find("\n")
                    s = self.buf[:idx + 1]
                    self.buf = self.buf[idx + 1:]
                    return s
                elif size < len(self.buf):
                    # Return at least 1 line in the first size bytes
                    idx = self.buf.rfind("\n", 0, size)
                    if idx >= 0:
                        s = self.buf[:idx + 1]
                        self.buf = self.buf[idx + 1:]
                        return s
            self._read_cv.acquire()
            try:
                try:
                    # no buffer available, block until we have something
                    self._client.notify('stdin')
                    self._read_cv.wait()
                    # always read from the start
                    if self.closed:
                        return None
                    io.StringIO.seek(self, 0)
                    data = self.buf + io.StringIO.readline(self, size)
                    io.StringIO.seek(self, 0)
                    io.StringIO.truncate(self)
                    return self._partition_data(data, size)
                except:
                    log.exception("big problemo in readline")
            finally:
                self._read_cv.release()

else:
    class StreamIn(StringIO.StringIO):
        def __init__(self, origStream, client):
            StringIO.StringIO.__init__(self, '')
            self._origStream = origStream
            self._read_cv = threading.Condition()
            self._client = client

        def __getattr__(self, attr):
            if self.__dict__.has_key(attr):
                return getattr(self.__dict__, attr)
            return getattr(self._origStream, attr)

        def stop(self):
            if not self.closed:
                StringIO.StringIO.close(self)
            return self._origStream

        def write(self, s):
            # 2011-11-23: When would this be called?  writing to an input stream?
            if self.closed:
                raise ValueError, "I/O operation on closed file"
            self._read_cv.acquire()
            try:
                # always write to the end
                StringIO.StringIO.seek(self, 0, os.SEEK_END)
                StringIO.StringIO.write(self, s)
                self._read_cv.notify()
            finally:
                self._read_cv.release()

        def read(self, size = -1):
            if self.closed:
                raise ValueError, "I/O operation on closed file"
            self._read_cv.acquire()
            try:
                if not self.buf:
                    # no buffer available, block until we have something
                    self._client.notify('stdin')
                    self._read_cv.wait()
                # always read from the start
                if self.closed:
                    return None
                StringIO.StringIO.seek(self, 0)
                x = StringIO.StringIO.read(self, size)
                # remove what we read from the stream
                # this ensures that reading from the beginning
                # will always give us new data, we're not in the
                # business of data storage here.
                self.buf = self.buf[self.pos:]
            finally:
                self._read_cv.release()
            return x

        def readline(self, size = None):
            if self.closed:
                raise ValueError, "I/O operation on closed file"
            self._read_cv.acquire()
            try:
                if not self.buf:
                    # no buffer available, block until we have something
                    self._client.notify('stdin')
                    self._read_cv.wait()
                # always read from the start
                if self.closed:
                    return None
                StringIO.StringIO.seek(self, 0)
                x = StringIO.StringIO.readline(self, size)
                # remove what we read from the stream
                # this ensures that reading from the beginning
                # will always give us new data, we're not in the
                # business of data storage here.
                self.buf = self.buf[self.pos:]
            finally:
                self._read_cv.release()
            return x

if sys.hexversion < 0x020300F0:
    # we only replace the original queue class if we're
    # running less than Python 2.3.  This allows us to
    # have a timeout so that the debugger threads do not
    # lock up on us if we attempt to kill the session

    # XXX for some reason, the Queue.Queue.get function from
    # 2.3 sources is a DOG under 2.2.  This code essentially
    # does the same thing but works great under 2.2.

    class TimedQueue(Queue.Queue):
        """TimedQueue enhanced Queue with wait timeouts

        The regular Queue only provides blocking or non-blocking
        access.  We need blocking with a timeout.
        """

        def __init__(self, maxsize=0):
            Queue.Queue.__init__(self, maxsize)
            self._waitCondition = threading.Condition()

        def put(self, item, block=1):
            # all we want to do here is notify blocking get
            # calls that we've put something in.  This releases
            # the condition faster.  We don't need a timeout
            # in the put, only in get.
            self._waitCondition.acquire()
            try:
                Queue.Queue.put(self, item, block)
                self._waitCondition.notify()
            finally:
                self._waitCondition.release()

        def get(self, block=1, timeout=None):
            """Remove and return an item from the queue with blocking.

            If we timeout, then toss an exception
            """
            # block is never used here, we rely on the
            # condition variables for blocking
            try:
                self._waitCondition.acquire()
                try:
                    # try non blocking first, then wait
                    return Queue.Queue.get(self, 0)
                except Queue.Empty, e:
                    if timeout is None and not block:
                        raise
                # ok, so we wait now
                self._waitCondition.wait(timeout)
                return Queue.Queue.get(self, 0)
            finally:
                self._waitCondition.release()
else:
    TimedQueue = Queue.Queue

class CommandError(Exception):
    """A simple exception that knows how to serialize itself to xml
    to facilitate sending a DBGP response for an error.
    """
    _cmd_error = '<response xmlns="urn:debugger_protocol_v1" command="%s" transaction_id="%s"><error code="%d"><message><![CDATA[%s]]></message></error></response>'

    def __init__(self, name, tid, errid, msg):
        self.name = name
        self.tid = tid
        self.errid = errid
        self.msg = msg
    def __str__(self):
        return self._cmd_error % (self.name,self.tid,self.errid,self.msg)

# validation functions used by the backend class
def _validateBreakpointType(client, bptype):
    if bptype not in ['line', 'call', 'return',
                      'exception', 'conditional', 'watch']:
        raise CommandError('','',ERROR_BREAKPOINT_TYPE,'invalid value for type')

def _validateBreakpointState(client, bpstate):
    if bpstate not in ['enabled','disabled','temporary','deleted']:
        raise CommandError('','',ERROR_BREAKPOINT_STATE,'invalid value for state')

def _validateStackDepth(client, depth):
    stack_depth = len(client.dbg.stack)
    if depth >= stack_depth:
        raise CommandError('','',ERROR_STACK_DEPTH,'Invalid stack depth %d requested, stack depth is %d' % (depth, stack_depth))

def _validateContextId(client, context_id):
    if context_id < 0 or context_id >= len(contextNames):
        raise CommandError('','',ERROR_CONTEXT_INVALID,'Invalid context id %d requested' % context_id)


# we need some stuff the regular breakpoint doesn't support, this
# provides it.  Basicaly we track the type and enabled status of
# the breakpoint, and a way to serialize the breakpoint to xml
breakpointsByNumber = [None]
class Breakpoint:

    """Breakpoint class

    Implements temporary breakpoints, ignore counts, disabling and
    (re)-enabling, and conditionals.

    Breakpoints are indexed by number through bpbynumber and by
    the file,line tuple using bplist.  The former points to a
    single instance of class Breakpoint.  The latter points to a
    list of such instances since there may be more than one
    breakpoint per line.

    The Breakpoint class also handles serializing breakpoints
    to xml for transport to the IDE.

    """

    def __init__(self, type, file = '', line = 0, enabled = 1, temporary=0,
                 cond = None, hitValue = None, hitCondition = None):
        self.type = type

        self.hitValue = hitValue
        if hitValue and not hitCondition:
            # this is the default value for hitCondition
            self.hitCondition = ">="
        else:
            self.hitCondition = hitCondition

        self.file = file    # This better be in canonical form!
        self.line = line
        self.temporary = temporary

        # depending on type, self.cond contains an expression,
        # function name or exception name
        self.cond = cond

        # if we're a watch bp, then we need to keep the
        # last known value here, so that we can see if
        # it changes
        self.lastValue = None

        self.enabled = enabled
        self.hits = 0
        self.number = -1
        # Build the two lists
        self.insert()

    def insert(self):
        if self.number < 0 or len(breakpointsByNumber) < self.number:
            breakpointsByNumber.append(self)
            self.number = len(breakpointsByNumber) - 1
        else:
            breakpointsByNumber[self.number] = self
        if breakpointList.has_key((self.file, self.line)):
            breakpointList[self.file, self.line].append(self)
        else:
            breakpointList[self.file, self.line] = [self]
        if breakpointsByFile.has_key(self.file):
            breakpointsByFile[self.file].append(self)
        else:
            breakpointsByFile[self.file] = [self]

    def deleteMe(self):
        index = (self.file, self.line)
        breakpointsByNumber[self.number] = None   # No longer in list
        breakpointList[index].remove(self)
        if not breakpointList[index]:
            # No more bp for this f:l combo
            del breakpointList[index]
        breakpointsByFile[self.file].remove(self)
        if not breakpointsByFile[self.file]:
            # No more bp for this f:l combo
            del breakpointsByFile[self.file]

    def enable(self):
        self.enabled = 1

    def disable(self):
        self.enabled = 0

    def toxml(self):
        """Return an XML representation of the breakpoint."""
        #XXX We are not yet handling the following attributes:
        #    function, exception
        tExpression = None
        tFunction = None
        tException = None
        if self.cond:
            if type in ['call', 'return']:
                tFunction = ' function="%s"' % self.cond
            elif type == 'exception':
                tException = ' exception="%s"' % self.cond
            elif type in ['conditional', 'watch']:
                tExpression = '<expression><![CDATA[%s]]></expression>' % self.cond

        bp =  '<breakpoint id="%s" type="%s"' % (self.number, self.type)
        bp += ' filename="%s" lineno="%s"' % (pathname2url(self.file), self.line)
        bp += ' state="%s"' % (self.enabled and 'enabled' or 'disabled')
        bp += ' temporary="%s"' % self.temporary
        if self.hitValue is not None:
            bp += ' hit_value="%s"' % self.hitValue
        if self.hitCondition is not None:
            bp += ' hit_condition="%s"' % escape(self.hitCondition)
        if tFunction:
            bp += tFunction
        if tException:
            bp += tException
        bp += '>'
        if tExpression:
            bp += tExpression
        bp += '</breakpoint>'

        return bp

def canonic(fname):
    canonic = canonicCache.get(fname)
    if canonic:
        return canonic
    if fname.startswith("<") and fname.endswith(">"):
        canonicCache[fname] = fname
        return fname

    canonic = os.path.abspath(fname)
    canonic = os.path.normcase(canonic)

    # Work around a problem where some filenames
    #  in Python code objects are relative.
    if not os.path.exists(canonic):
        fullname = None

        # Try looking through the module search path
        for dirname in sys.path:
            testname = os.path.join(dirname, fname)
            if os.path.exists(testname):
               canonic = os.path.abspath(testname)
               canonic = os.path.normcase(canonic)
               break

    canonicCache[fname] = canonic
    return canonic

# Determines if there is an effective (active) breakpoint at this
# line of code.  Returns breakpoint number or 0 if none
def effective(frame, arg, type):
    """Determine which breakpoint for this file:line is to be acted upon.

    Returns breakpoint that was triggered and a flag
    that indicates if it is ok to delete a temporary bp.

    """
    file = canonic(_filename_from_frame(frame))
    if not breakpointsByFile.has_key(file):
        return (None, None)

    line = frame.f_lineno

    possibles = []
    if breakpointList.has_key((file, line)):
        possibles += breakpointList[file, line]
    if breakpointList.has_key((file, 0)):
        possibles += breakpointList[file, 0]
    if breakpointList.has_key(('', 0)):
        possibles += breakpointList['', 0]

    # reduce list by type if we have a type
    if type:
        possibles = [bp for bp in possibles if bp.type == type]

    if not possibles:
        return (None, None)

    exNames = None

    for i in range(0, len(possibles)):
        b = possibles[i]
        if b.enabled == 0:
            continue

        val = None
        if b.cond:
            if b.type == 'conditional':
                # Conditional bp.
                # hits and hitValue applies only to those bp
                # hits where the condition evaluates to true.
                try:
                    val = eval(b.cond, frame.f_globals,
                           frame.f_locals)
                except:
                    # if eval fails, most conservative
                    # thing is to stop on breakpoint
                    # regardless of ignore count.
                    # Don't delete temporary,
                    # as another hint to user.
                    return (b, 0)
                if not val:
                    # conditionals are only a hit if they
                    # eval to true, so continue to the
                    # next breakpoint
                    continue

            elif b.type == 'watch':
                # for watched breaks, we eval the condition, and if it
                # is not the same as the last value, then it has changed
                # and we must break.

                # this does not exactly match a watch where you want to
                # break when a value changes, but is as close an
                # aproximation as we can get until python supports this
                # internally.
                try:
                    value = eval(b.cond, frame.f_globals, frame.f_locals)
                except:
                    # we don't care about any exceptions here, we just
                    # want a value if it exists
                    continue

                if value == b.lastValue:
                    continue
                b.lastValue = value

            elif type:
                # we'll only do these if a type was defined
                if b.type in ['call', 'return']:
                    # arg is none for call
                    # arg is return type for return
                    if frame.f_code.co_name != b.cond:
                        continue
                elif b.type == 'exception':
                    # arg = (exception, value, traceback)
                    if not exNames:
                        # if we cannot get the exception names, then
                        # return no breakpoint
                        exNames = _class_names(arg[0])
                        if not exNames:
                            return (None, None)
                    if b.cond not in exNames.values():
                        continue
                else:
                    continue
            else:
                continue

        # Count every hit when bp is enabled
        b.hits = b.hits + 1

        # handle hitValue/hitConditions
        if b.hitValue:
            if b.hitCondition == '>=':
                if b.hits < b.hitValue:
                    continue
            elif b.hitCondition == '==':
                if b.hits != b.hitValue:
                    continue
            elif b.hitCondition == '%':
                import operator
                if operator.mod(b.hits, b.hitValue):
                    continue
            else:
                # invalid hitCondition, we'll just ignore it
                # since we might not support all the condition
                # types that an IDE might send us
                pass

        # breakpoint and marker that's ok
        # to delete if temporary
        return (b, 1)
    return (None, None)

if _is_py3:
    def base64_encodestring(data):
        """  In Python 3 this method expects bytes and returns bytes,
        but we need a string, as we're building up a string which
        we'll eventually encode when writing to a socket
        """
        return base64.encodebytes(data).decode()
    def base64_decodestring(data):
        """  Again, we're given characters, and need to return characters.
        """
        return base64.decodebytes(data.encode()).decode()
else:
    def base64_encodestring(data):
        return base64.encodestring(data)
    def base64_decodestring(data):
        return base64.decodestring(data)

def Property(name, fullname, value, encoding='base64',
             include_private=0, include_hiddenTypes=None):
    # Bug 94782 -- better support for numpy
    typeName = str(type(value))
    if typeName.startswith("<type 'numpy") and not include_hiddenTypes:
        if typeName.startswith("<type 'numpy.ndarray"):
            return NumpyNdarrayProperty(name, fullname, value, encoding,
                                        include_private, include_hiddenTypes)
        else:
            return NumpyOtherProperty(name, fullname, value, encoding,
                                        include_private, include_hiddenTypes)

    else:
        return StandardProperty(name, fullname, value, encoding,
                                include_private, include_hiddenTypes)

class StandardProperty:
    """DBGP Python Property class.

    a class to serialize python data types into xml
    handles children of objects/arrays/etc.
    """

    def __init__(self, name, fullname, value, encoding = 'base64',
                 include_private=0, include_hiddenTypes=None):
        # protect against new types
        self.name = name
        self.fullname = fullname
        self.value = self.original_value = value
        self._children = None
        self._numchildren = None
        self.encoding = encoding
        self.include_private = include_private # to show __X__ names also
        # if examining a module, then let us see the children.  This should actually
        # be a type from the types module
        self.include_hiddenTypes = include_hiddenTypes

    _ws_ptn = re.compile("[\t\r\n]")
    def _hex_encode(self, match):
        return "\\x%02X" % ord(match.group(0))
    def _ws_escape(self, data):
        return self._ws_ptn.sub(self._hex_encode, data)

    def _xmlcharref(self, m):
        return "&#x%0x;" % ord(m.group(1))

    _should_be_base64_encoded__ctrl_char_re = re.compile(r'[\x00-\x08\x0b\x0c\x0d\-x0e\x10-\x1f]')
    _should_be_base64_encoded__high_bit_re = re.compile(r'[^\x00-\xff]')
    def _should_be_base64_encoded(self, data):
        if _is_py3 and type(data) == types.StringType: # types.StringType 2=>3 bytes
            data = data.decode('utf-8')
        return ('<![CDATA[' in data
                or ']]>' in data
                or self._should_be_base64_encoded__ctrl_char_re.search(data)
                or self._should_be_base64_encoded__high_bit_re.search(data))

    charRefPtn = re.compile(r'([^\x00-\x7f])')
    def _get_encodedData(self, data):
        # First, convert byte-strings into unicode
        # If we can't utf8-decode them, assume latin1
        if ((_is_py3 and type(data) == bytes)
            or (not _is_py3 and type(data) == str)):
            try:
                data = data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    data = data.decode('latin1')
                except UnicodeDecodeError:
                    pass
        if self.encoding != 'base64':
            encodeAsBase64 = False
        elif (not _is_py3) or type(data) == types.UnicodeType: # types.UnicodeType 2=>3 str
            encodeAsBase64 = self._should_be_base64_encoded(data)
        else:
            encodeAsBase64 = True
        if ((_is_py3 and type(data) == types.UnicodeType)
            or ((not _is_py3) and type(data) in (types.StringType, types.UnicodeType))):
            try:
                data = data.encode('utf-8')
            except:
                try:
                    # Manually encode it, since xmlcharrefreplace doesn't seem to work
                    data = self.charRefPtn.sub(self._xmlcharref, data)
                except:
                    data = "?" * len(data)
        if encodeAsBase64:
            return base64_encodestring(data), self.encoding
        return escape(data), None

    def get_encodedName(self):
        return self._get_encodedData(self.name)

    def get_encodedFullname(self):
        return self._get_encodedData(self.fullname)

    def _construct_name_tag(self, tagName, valuePayload, encoding):
        if encoding:
            return '<%s encoding="%s"><![CDATA[%s]]></%s>' % (tagName, encoding, valuePayload, tagName)
        else:
            return '<%s><![CDATA[%s]]></%s>' % (tagName, valuePayload, tagName)

    def get_encodedValue(self, maxdata = 0):
        # maxdata constraint, so we cannot use _get_encodedData
        data = self.value
        if maxdata:
            data = self.value[:maxdata]
        return self._get_encodedData(data)

    def get_type(self):
        typ = type(self.original_value)
        if not _is_py3 and typ == types.InstanceType:
            cn = _class_names(self.original_value)
            if cn is None:
                # See bug 88435
                return None
            typ = cn.get('name', None) or cn.get('fullname', None) or typ
        return typ

    def get_typeString(self):
        typeName = self.get_type()
        try:
            return typeName.__name__
        except AttributeError:
            return str(typeName)

    def get_dataSize(self):
        try:
            if '__len__' not in dir(self.value):
                return 0
            return len(self.value)
        except:
            return 0

    def get_valueString(self):
        try:
            return repr(self.value)
        except:
            # XXX raise a CommandError exception?
            return "Looking at object failed - %s: %s" % (sys.exc_info()[0], sys.exc_info()[1])

    def get_numchildren(self):
        if self._numchildren is not None:
            return self._numchildren
        self._numchildren = 0
        # checking for properties should catch the vast majority of cases!
        typ = self.get_type()
        if typ is not None and typ not in BaseTypes:
            # count the children and set into numchildren
            self.get_children(1)
        return self._numchildren

    def get_children(self, countOnly=0):
        if self._children is not None:
            return self._children

        if type(self.value) in HiddenTypes and \
           type(self.value) not in self.include_hiddenTypes and \
           not self.include_private:
            return []

        self._numchildren = 0
        children = []
        _val_dir = dir(self.value)
        for childStr in _val_dir:
            if ((not self.include_private) and \
               (childStr[:1] == '_')) or \
               childStr == "__builtins__":
                continue
            try:
                # bug 83896 -- treat properties as non-eval-able objects.
                # We want to display them, but make sure the debugger
                # doesn't call their getters
                propObj = getattr(self.value.__class__, childStr)
                if type(propObj) == property:
                    self._numchildren += 1
                    if not countOnly:
                        c = Property(childStr,
                                     "%s.%s" % (self.name, childStr),
                                     propObj,
                                     self.encoding,
                                     self.include_private,
                                     self.include_hiddenTypes)
                        # Clear the children count to prevent the debugger from
                        # invoking the getter when the user tries to expand this variable.
                        # properties don't have interesting children anyway - they hide them.
                        c._numchildren = 0
                        children.append(c)
                    continue
            except:
                pass
            try:
                child = getattr(self.value, childStr)
            except:
                self._numchildren += 1
                if countOnly: continue
                c = Property(childStr,
                             "%s.%s" % (self.name,childStr),
                             None, self.encoding,
                             self.include_private,
                             self.include_hiddenTypes)
                children.append(c)
            else:
                cvalue = _safe_apply("Getting attribute failed",
                                    getattr, self.value, childStr)
                if self.include_hiddenTypes or type(cvalue) not in HiddenTypes:
                    self._numchildren += 1
                    if countOnly: continue
                    c = Property(childStr,
                                 "%s.%s" % (self.name,childStr),
                                 cvalue, self.encoding,
                                 self.include_private,
                                 self.include_hiddenTypes)
                    children.append(c)

        # handle tuples, dicts and lists
        # we always show a value for these types, even if it is in the hidden types list
        if '__getitem__' in _val_dir:
            #log.debug("value has __getitem__")
            if 'keys' in _val_dir:
                #log.debug("value has keys")
                try:
                     # repr introduces quotes if the object is already a string
                     # (but the object may be one being debugged, and its repr
                     # may fail!  This wouldn't be good, as it looks like the
                     # debugger failed!
                     # XXX Shouldn't return all of really big mappings but how
                     # do we know what part the user is interested in?
                    child_keys = self.value.keys()
                    self._numchildren += len(child_keys)
                    if not countOnly:
                        for child in child_keys:
                            cvalue = _safe_index("child", self.value, child)
                            # Python bug 5425: types.StringTypes considered bogus,
                            # as most other types fields give a single value
                            if type(child) not in (types.UnicodeType, types.StringType):
                                cname = _safe_apply("repr", repr, child)
                            else:
                                cname = "'%s'" % child.replace("'","\'")
                            c = Property(cname,
                                         "%s[%s]" % (self.name,cname),
                                         cvalue, self.encoding,
                                         self.include_private,
                                         self.include_hiddenTypes)
                            children.append(c)
                except:
                    # The users sequence object returned by keys is raising
                    # exceptions, so let's just give up
                    pass

            # value doesn't seem to be a mappying-like thing, let's see
            # if it is a sequence-like thing
            elif '__len__' in _val_dir:
                #log.debug("value has __len__")
                try:
                    vlen = len(self.value)
                    self._numchildren += vlen
                    if not countOnly:
                        for child in range(vlen):
                            cvalue = _safe_index("object", self.value, child)
                            c = Property("[%d]" % child,
                                         "%s[%d]" % (self.name,child),
                                         cvalue, self.encoding,
                                         self.include_private,
                                         self.include_hiddenTypes)
                            children.append(c)
                except:
                    pass

        if countOnly: return None

        self._children = children
        return children

    def get_hasChildren(self):
        return int(self.get_numchildren() > 0)

    def toxml(self, depth = MAX_DEPTH, maxchildren = MAX_CHILDREN, maxdata = MAX_DATA, page = 0):
        childprops = []
        numchildren = self.get_numchildren()
        haschildren = self.get_hasChildren()
        if depth > 0 and numchildren > 0:
            start = page * maxchildren
            end = start + maxchildren
            if end >= numchildren:
                end = numchildren
            #print "numchildren %s" % (numchildren)
            #print "max children %s" % (maxchildren)
            #print "page %s" % (page)
            #print "getting %d children" % (end-start)
            childprops = [child.toxml(depth-1, maxchildren, maxdata, 0)
                          for child in self.get_children()[start:end]]

        vType = type(self.value)
        if not self.include_private and \
           vType not in self.include_hiddenTypes and \
           numchildren > 0 and not childprops and depth > 0:
            numchildren = 0
            haschildren = 0

        value = ''
        encodeAsCData = False
        if vType not in StringTypes:
            if numchildren == 0 or vType in HiddenTypes:
                # Removed when writing the py3 port:
                # or vType == types.InstanceType
                # This means instance repr's appear only when the code
                # object has no children.
                data = self.value = self.get_valueString()[:maxdata]
                if self._should_be_base64_encoded(data):
                    encodeAsCData = True
                else:
                    value = '<value><![CDATA[%s]]></value>' % (data,)
            else:
                try:
                    stringified_value = str(self.value)
                    if ' object at 0x' not in stringified_value:
                        self.value = stringified_value
                        encodeAsCData = True
                except:
                    log.info("Failed to str %r", self.value)
        else:
            encodeAsCData = True
        if encodeAsCData:
            data, encoding = self.get_encodedValue(maxdata)
            value = '<value encoding="%s"><![CDATA[%s]]></value>'  % (encoding, data)

        #XXX
        # Rewrite this code to make it clearer:
        # if vType in StringTypes: emit string type
        # elif numchildren == 0 or it has a value
        #       (vType in HiddenTypes or vType == types.InstanceType):
        #   evaluate as a string, emit base64-encoded
        #   -- because repr strings can contain XML tex.
        # else pass, say why we aren't emitting a value
        #
        # Most likely it's an optimization

        name, encoding = self.get_encodedName()
        childprops.append(self._construct_name_tag("name", name, encoding))
        fullname, encoding = self.get_encodedFullname()
        childprops.append(self._construct_name_tag("fullname", fullname, encoding))

        value = value + ''.join(childprops)
        attrs = {'type': self.get_typeString(),
                 'children': haschildren,
                 'size': self.get_dataSize()}
        if numchildren > 0:
            attrs['page'] = page
            attrs['pagesize'] = maxchildren
            attrs['numchildren'] = numchildren

        return '<property %s>%s</property>' % (_getAttrStr(attrs), value)


class NumpyNdarrayProperty(StandardProperty):
    """
    Numpy objects are complex wrappers around standard Python objects.
    Unless the user asks to see all attributes, the Python debugger uses
    this wrapper class around arrays, and the NumpyOtherProperty class
    for all other object types, to present a more useful view of the
    objects.
    Note that property_set works as usual.
    """
    def get_encodedValue(self, maxdata = 0):
        # maxdata constraint, so we cannot use _get_encodedData
        data = self.get_valueString()
        if maxdata:
            data = self.value[:maxdata]
        return self._get_encodedData(data)

    def get_valueString(self):
        try:
            return "%s: %s" % (type(self.value).__name__, self.value)
        except:
            # XXX raise a CommandError exception?
            return "Looking at object failed - %s: %s" % (sys.exc_info()[0], sys.exc_info()[1])

    def get_numchildren(self):
        return len(self.value)

    def get_children(self, countOnly=0):
        # Return only the data items, not all the other attributes
        # Too bad get_children returns all of them, and then toxml selects the
        # ones it wants.  Better if get_children selected fewer items.
        if self._children is not None:
            return self._children
        self._numchildren = self.get_numchildren()
        if countOnly:
            return None
        self._children = [Property("%s" % i,
                                   "%s[%s]" % (self.name, i),
                                   self.value[i],
                                   self.encoding,
                                   self.include_private,
                                   self.include_hiddenTypes) for i in range(self._numchildren)];
        return self._children

class NumpyOtherProperty(StandardProperty):

    def __init__(self, *args, **kwargs):
        StandardProperty.__init__(self, *args, **kwargs)
        self._hasEncodedNumpyValue = False
        self._encodedNumpyValue = None

    def get_encodedValue(self, maxdata = 0):
        # maxdata constraint, so we cannot use _get_encodedData
        data = self.get_valueString()
        if maxdata:
            data = self.value[:maxdata]
        return self._get_encodedData(data)

    def get_valueString(self):
        try:
            return "%s" % (self._numpy_to_python_value())
        except:
            # XXX raise a CommandError exception?
            return "Looking at object failed - %s: %s" % (sys.exc_info()[0], sys.exc_info()[1])

    def get_numchildren(self):
        return 0

    def _numpy_to_python_value(self):
        if not self._hasEncodedNumpyValue:
            self._encodedNumpyValue = self._finish_numpy_to_python_value()
            self._hasEncodedNumpyValue = True
        return self._encodedNumpyValue

    def _finish_numpy_to_python_value(self):
        try:
            value = self.value
            prefixPart = len("<type 'numpy.")
            # Drop the trailing "'>"
            valueType = str(type(value))[prefixPart:-2]
            if valueType.startswith("long"):
                valueType = valueType[4:]
            elif valueType.startswith("uint"):
                valueType = valueType[1:]
            elif valueType == "ulonglong":
                valueType = "long"

            if valueType == "ndarray":
                return [value[i] for i in range(len(value))]
            if valueType.startswith("int"):
                return int(value)
            if valueType.startswith("bool"):
                return bool(value)
            if valueType.startswith("double") or valueType.startswith("float"):
                return float(value)
            if valueType == "long":
                return long(value)
            if valueType == "short":
                return int(value)
            if valueType.startswith("string") or valueType.startswith("unicode"):
                return str(value)
            if valueType.startswith("void"):
                return None
        except:
            log.exception("Failure to get numpy value")
        return str(value)


class dbgpClient(clientBase):

    """DBGP Python debugger base class.

    This class takes care of details of the trace facility;
    """

    fncache = {}

    def __init__(self, requester, ignoreList=[], module=None):
        ignoreModules = ignoreList

        clientBase.__init__(self)
        self._interactiveDebugger = None

        self.requester = requester
        self._threadStart = 0
        self.main_module = module
        self.forget()

    def reset(self):
        self.botframe = None
        self.stopframe = None
        self.returnframe = None
        self.quitting = 0

    # Override the dbd set_* functions to manage our bottom frame fix.
    def set_step(self):
        self.botframeBehaviour = BOTFRAME_STEP
        self.stopframe = None
        self.returnframe = None
        self.quitting = 0

    def set_next(self, frame):
        # A "step over" operation - if we are at the bottom frame,
        # then we need to be in step mode.
        if frame is self.botframe:
            self.botframeBehaviour = BOTFRAME_STEP
        self.stopframe = frame
        self.returnframe = None
        self.quitting = 0

    def set_return(self, frame):
        # A "step out" operation - if the frame we are returning to is
        # the bottom frame, then we need to be in step mode.
        if frame.f_back is self.botframe:
            self.botframeBehaviour = BOTFRAME_STEP
        elif frame is self.botframe:
            # At the bot-frame and stepping out - like a "run"
            self.botframeBehaviour = BOTFRAME_CONTINUE
        self.stopframe = frame.f_back
        self.returnframe = frame
        self.quitting = 0

    def set_trace(self):
        """Start debugging from here."""
        frame = sys._getframe().f_back
        self.reset()
        while frame:
            if not frame.f_globals.has_key('DBGPHide'):
                if hasattr(self,'trace_dispatch'):
                    frame.f_trace = self.trace_dispatch
                else:
                    frame.f_trace = self
                self.botframe = frame
            frame = frame.f_back
        self.set_step()
        self.starttrace()

    def set_continue(self):
        # Don't stop except at breakpoints or when finished
        self.botframeBehaviour = BOTFRAME_CONTINUE
        self.stopframe = None
        self.returnframe = None
        self.quitting = 0

    def set_quit(self):
        self.botframeBehaviour = BOTFRAME_CONTINUE
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = 1
        self.stoptrace()

    def set_break(self, type, filename, lineno, enabled, temporary=0,
                  cond=None, hitValue=None, hitCondition=None):
        import linecache # Import as late as possible
        if filename:
            filename = canonic(filename)
            # some breakpoint types do not have line numbers
            if lineno:
                line = linecache.getline(filename, lineno)
                if not line:
                    raise DBGPError('Line %s:%d does not exist' % (filename, lineno))
        return Breakpoint(type, filename, lineno, enabled, temporary, cond,
                          hitValue, hitCondition)

    def get_stack(self, f, t):
        stack = []
        if t and t.tb_frame is f:
            t = t.tb_next
        while f is not None:
            if f.f_builtins.has_key('DBGPHideChildren') and \
               f.f_builtins['DBGPHideChildren']:
                # clear the stack of the children
                stack = []
            if _hide_stack(f) or f.f_lineno == 0:
                f = f.f_back
                continue

            stack.append((f, f.f_lineno))

            f = f.f_back
        stack.reverse()

        # <<max(0, len(stack) - 1)>> sometimes throws an exception.
        i = len(stack) - 1
        if i < 0:
            i = 0
        while t is not None:
            if not _hide_stack(t.tb_frame):
                stack.append((t.tb_frame, t.tb_lineno))
            t = t.tb_next

        # when using interactive shell, we dont have a stack frame, we use a fake
        # frame instead, which maintains our globals and locals across interactions
        if not stack and self._interactiveDebugger:
            stack.append((self._interactiveDebugger.frame, 0))

        return stack, i

    def setup(self, f, t):
        self.forget()
        self.stack, self.curindex = self.get_stack(f, t)
        self.stack.reverse()

    def forget(self):
        self.stack = []
        if self._interactiveDebugger:
            self.stack.append((self._interactiveDebugger.frame, 0))
        self.curindex = 0

    def interaction(self, frame, tb = None, async = 0):
        self.interrupt = 0
        self.setup(frame, tb)
        try:
            return self.requester.cmdloop(async)
        finally:
            self.forget()
        return RESUME_STOP

    def dispatch_interaction(self, frame, arg = None):
        if os.name == 'java':
            f = sys._getframe()
            while f.f_back:
              f = f.f_back
            # if the very top item on the stack is __del__
            # then we must be in a Jython finalization thread
            # ignore it!
            if f.f_code.co_name == "__del__":
                return

        rc = self.interaction(frame)
        if rc == RESUME_STOP:
            self.set_quit()
            sys.exit(-1)
        elif rc == RESUME_STEP_IN:
            self.set_step()
        elif rc == RESUME_STEP_OVER:
            self.set_next(frame)
        elif rc == RESUME_STEP_OUT:
            self.set_return(frame)
        elif rc == RESUME_GO:
            self.set_continue()
        else:
            raise Exception("Unknown resume state %r" % rc)

    # The following two methods can be called by clients to use
    # a debugger to debug a statement, given as a string.

    def run(self, cmd, globals=None, locals=None, module=None):
        if module is None:
            module = self.main_module
        self.reset()
        try:
            try:
                h_exec(cmd, globals=globals, locals=locals, module=module, tracer=self)
            except DBGPQuit:
                pass
        finally:
            self.quitting = 1

    def runfile(self, file, args, main=None):
        if main is None:
            main = self.main_module
        self.reset()
        try:
            try:
                h_execfile(file, args, module=main, tracer=self)
            except DBGPQuit:
                pass
        finally:
            self.quitting = 1

    def runeval(self, expr, globals=None, locals=None, module=None):
        if module is None:
            module = self.main_module
        self.reset()
        try:
            try:
                return h_eval(expr, globals=globals, locals=locals, module=module, tracer=self)
            except DBGPQuit:
                pass
        finally:
            self.quitting = 1

    # This method is more useful to debug a single function call.
    def runcall(self, func, args, kwargs):
        self._threadStart = 1
        self.reset()
        self.starttrace()
        res = None
        try:
            try:
                res = apply(func, args, kwargs)
            except DBGPQuit:
                pass
        finally:
            self.stoptrace()
            self.quitting = 1
        return res

    # this allows debuging code without having exceptions set
    # the quiting flag
    def runcode(self, code, globals=None, locals=None, module=None):
        if module is None:
            module = self.main_module

        # we do not debug interactive code, as that has not been
        # tested and dealt with correctly.  It's also much faster if we dont
        self.stoptrace()
        try:
            try:
                h_exec(code, globals=globals, locals=locals, module=module)
            except DBGPQuit:
                self.quitting = 1
        finally:
            if not self.quitting:
                self.starttrace()

    def getInteractiveDebugger(self, main=None):
        if not main:
            main = self.main_module
        if not self._interactiveDebugger:
            # we always pick the top level stack and use the globals for
            # everything.  Interacting does not happen at different points
            # in the stack
            frame = None
            try:
                frame, lineno = self.stack[0]
            except IndexError, e:
                pass
            if not frame:
                # looks like we were started in interactive mode
                frame = FakeFrame(main.globals, main.locals)
            self._interactiveDebugger = InteractiveDebugger(self, frame)
        return self._interactiveDebugger

    def releaseInteractiveDebugger(self):
        self._interactiveDebugger = None

_clientInstances = {}

def registerClient(client):
    global _clientInstances
    _clientInstances[client.thread_id] = client

def deregisterClient(client):
    #print "deregister ",client.thread_id
    global _clientInstances
    if _clientInstances.has_key(client.thread_id):
        del _clientInstances[client.thread_id]

def warnMainThreadEnding():
    global _clientInstances
    if len(_clientInstances) > 0:
        # Allow some time for Komodo's dbgp thread wrappers to finish.
        import time
        time.sleep(1)
        if len(_clientInstances) > 0:
            log.error("""
The main thread of this application is exiting while there are still threads
alive. When the main thread exits, it is system defined whether the other
threads survive.

See Caveats at http://docs.python.org/lib/module-thread.html
""")


def getClientForThread():
    # this is tricky.  we have to dig back through the frames to find our
    # clientInstances variable, then use the client for this thread if there
    # is one available.
    frame = sys._getframe().f_back
    # find a dbgp stack frame
    while frame and frame.f_back:
        if '_clientInstances' in frame.f_globals:
            ci = frame.f_globals['_clientInstances']

            tid = thread.get_ident()
            if tid in ci:
                return ci[tid]
        frame = frame.f_back
    return None

class dbgpSocket:
    socket_type = None
    hostname = None
    port = 0
    orig_stdin = None
    notify_ok = 0
    def __init__(self, mainThread, hostname = '', port = 9000, socket_type=socket.AF_INET):
        self.queue = TimedQueue()
        self.mainThread = mainThread
        # override stdin so we can send notifications
        if not dbgpSocket.orig_stdin:
            dbgpSocket.orig_stdin = sys.stdin
            sys.stdin = StreamStdin(dbgpSocket.orig_stdin, self)
        if dbgpSocket.hostname is None:
            dbgpSocket.hostname = hostname
            dbgpSocket.port = port
            dbgpSocket.socket_type = socket_type

    def connect(self):
        # connect to the host, then wait for the first header
        # sent from the host and process it
        try:
            self._socket = socket.socket(self.socket_type, socket.SOCK_STREAM)
            self._socket.connect((self.hostname,self.port))
        except socket.error, e:
            sys.stderr.write("dbgpSocket: error: unable to connect to remote host at %s:%d\n\n"% (self.hostname,self.port))
            raise
        self._stop = 0
        self._startCommandThread()

    def stop(self):
        self._stop = 1
        self.queue.put(None)
        if self._socket:
            self._socket.close()
            self._socket = None

    def _getIncomingDataPacket(self):
        # _getIncomingDataPacket needs to be in a thread that
        # stuffs incoming packets into a queue.
        # _getIncomingDataPacket should also dispatch
        # calls for stdin so we can debug raw_input
        log.debug("_getIncomingDataPacket starting...")
        # gets the next chunk of data until a null byte is
        # encountered
        data = ''
        while not self._stop:
            log.debug("_getIncomingDataPacket getting data...")
            try:
                newData = self._socket.recv(1024)
                if _is_py3:
                    newData = newData.decode()
                data = data + newData
            except socket.error, e:
                # socket was closed on us, quit now
                log.debug("_getIncomingDataPacket socket closed")
                self.queue.put(None)
                break
            if not data:
                # protocol error, we should never receive an empty
                # data set
                log.debug("_getIncomingDataPacket socket closed")
                self.queue.put(None)
                break
            log.debug("    %d[%r]" , len(data), data)

            while data:
                eop = data.find('\0')
                if eop < 0:
                    break

                cmddata = data[:eop]
                data = data[eop+1:] # skip \0

                argv = listcmd.line2argv(cmddata)

                log.debug("    put data in queue [%r]", cmddata)
                # stdin blocks the executing thread, so we have to do the async
                # stdin call here.  This only happens with remote debugging when
                # stdin is redirected.
                if argv[0] in ['stdin', 'stop']:
                    self.mainThread.onecmd(argv, 'do_async_')
                else:
                    self.mainThread.dbg.interrupt = 1
                    self.queue.put(argv)

        log.debug("_getIncomingDataPacket exiting...")

    def _startCommandThread(self):
        _nonDebugThread(self._getIncomingDataPacket, ())

    def send_response(self, response):
        if self._stop:
            return
        header = u'<?xml version="1.0" encoding="utf-8"?>\n'
        response = (header+response)
        try:
            response = response.encode('utf-8')
        except (UnicodeEncodeError,UnicodeDecodeError), e:
            pass
        #log.debug('sending [%r]', response)
        try:
            self._socket.send(_encode_response(response))
        except socket.error, e:
            self.stop()

    def notify(self, name, data=None):
        if not self.notify_ok: return
        out = '<notify xmlns="urn:debugger_protocol_v1" name="%s"' % name
        if data:
            out += '>%s</notify>' % data
        else:
            out += '/>'
        self.send_response(out)


class backend(listcmd.ListCmd):
    # this is the base communications class.  It handles reading
    # and writing data to the sockets, dispatching of commands,
    # communication, etc.  Command implementations are in
    # the backendCmd subclass below
    ide_key = ''
    destination_id = 0
    source_id = 0
    appid = None
    parent_appid = ''
    _stop = 0

    # application wide configuration
    _encoding = 'utf-8'
    _data_encoding = 'base64'

    def __init__(self, idekey = 0, preloadScript = None, ignoreModules = [], module=None):
        listcmd.ListCmd.__init__(self)
        self.stdin_enabled = 1
        self._preloadScript = preloadScript

        self._stdin = None
        self._stdout = None
        self._stderr = None
        self._continue = RESUME_STOP
        self._continueTransactionId = None
        self._continuationCommand = None
        self._break_reason = REASON_OK
        self._break_status = STATUS_STOPPED
        self._lastErrorMessage = ''
        self._detach = 0
        self.thread_id = thread.get_ident()
        if not backend.appid:
            if hasattr(os, 'getpid'):
                backend.appid = os.getpid()
            else:
                # Jython doesn't provide getpid(), so we
                # have to have _something_
                backend.appid = 1
            backend.parent_appid = getenv("DEBUGGER_APPID", '')
            if hasattr(os, 'putenv'):
                os.putenv('DEBUGGER_APPID',str(backend.appid))
        self.filename = ''
        if idekey:
            backend.ide_key = idekey

        # interactive debugger support
        self._interactiveBuffer = []
        self._isInteractiveShell = 0

        registerClient(self)
        self.dbg = dbgpClient(self, ignoreModules, module=module)

    def emptyline(self):
        pass

    def connect(self, hostname = '', port = 9000, name = 'unknown',
                args = ['interactive'], socket_type=socket.AF_INET):
        self.socket = dbgpSocket(self, hostname, port, socket_type)
        self.socket.connect()
        self.sendInit(name, args[0])

    def notify(self, name, data=None):
        self.socket.notify(name, data)

    def stopNow(self):
        self._stop = self._detach = 1
        self.dbg.stoptrace()
        self.socket.stop()

    def detachNow(self):
        self._detach = 1
        set_thread_support(None)
        self.dbg.stoptrace()
        self.socket.stop()

    def close(self):
        self.stopNow()

    def atexit(self):
        # signal the IDE that we're stopping
        self._break_status = STATUS_STOPPING
        self.send_continuationResult(self._continue, STATUS_STOPPING, REASON_OK)

        if not self._stop:
            # we want to stop now until the IDE chooses to end the session
            while not self._detach:
                self.cmdloop()

        if self._stdin:
            sys.stdin = self._stdin.stop()
        self._stop = self._detach = 1
        self.dbg.stoptrace()
        self.dbg = None

    def breakNow(self):
        self._break_status = STATUS_BREAK
        frame = sys._getframe().f_back
        self.dbg.setup(frame, None)
        self.dbg.set_trace()

    def preloadScript(self, locals):
        if not self._preloadScript:
            return

        # Ready to roll - do it.
        code = open(self._preloadScript).read()

        # python expects lines to end with '\n' only so kill the '\r's
        code = code.replace('\r\n', '\n')
        code = code.replace('\r', '\n')

        # there's also an issue with files that don't end with newlines, so tag on a few
        code = code + '\n\n\n'

        # let this throw an exception if it fails
        exec code in locals, locals

    def runExceptHook(self, type, value, traceback):
        self._isInteractiveShell = 1 # exit when shell is stopped
        self._break_status = STATUS_INTERACTIVE
        self.dbg.setup(None, traceback)

        # do a command loop until we're stopped
        while not self._detach and not self._stop:
            self.cmdloop()

        self.dbg = None

    def runInteractive(self):
        self._isInteractiveShell = 1
        self._break_status = STATUS_INTERACTIVE

        # force the interactive debugger to be created so we have a frame available
        self.dbg.getInteractiveDebugger()
        self.dbg.reset()
        self.dbg.forget() # reset the stack so we have our fake stack available
        self.dbg.set_continue()
        self.dbg.starttrace()

        # do a command loop until we're stopped
        while not self._detach and not self._stop:
            self.cmdloop()

        self.dbg = None

    def runThread(self, target, args, kargs):
        # threads start in run mode
        self._break_status = STATUS_STARTING
        res = None
        try:
            res = self.dbg.runcall(target, args, kargs)
            self.send_continuationResult(self._continue, STATUS_STOPPING, REASON_OK)
        except SystemExit, e:  # if someone does a sys.exit(), it's not really an exception.
            self.send_continuationResult(self._continue, STATUS_STOPPED, REASON_ABORTED)
            raise
        except:
            #traceback.print_exc()
            _print_exc()
            self.send_continuationResult(self._continue, STATUS_STOPPING, REASON_EXCEPTION)

        if not self._stop:
            # we want to stop now until the IDE chooses to end the session
            while not self._detach:
                self.cmdloop()

        self.dbg = None
        deregisterClient(self)
        return res

    def runMain(self, debug_args, interactive=0):
        if interactive:
            end_status = STATUS_INTERACTIVE
        else:
            end_status = STATUS_STOPPING

        self._break_status = STATUS_STARTING

        try:
            self.preloadScript(locals)
            self.dbg.runfile(debug_args[0], debug_args)
            if not (self._stop or self._detach):
                self.send_continuationResult(self._continue, end_status, REASON_OK)
        except SyntaxError, e:
            _print_exc()
            if not (self._stop or self._detach):
                self.send_continuationResult(self._continue, end_status, REASON_EXCEPTION)
            self._stop = self._detach = 1
            self.dbg.stoptrace()
        except SystemExit, e:  # if someone does a sys.exit(), it's not really an exception.
            if not (self._stop or self._detach):
                self.send_continuationResult(self._continue, end_status, REASON_ABORTED)
            raise
        except:
            # uncaught exception, enter interactive mode
            #traceback.print_exc()
            _print_exc()
            tb_info = sys.exc_info()
            end_status = STATUS_INTERACTIVE
            self.dbg.setup(None, tb_info[2])
            self.dbg.getInteractiveDebugger()
            interactive = 0 # we don't want that logic
            self._isInteractiveShell = 1 # stopping the shell stops debugger
            if not (self._stop or self._detach):
                self.send_continuationResult(self._continue, end_status, REASON_EXCEPTION)

        if interactive:
            self._isInteractiveShell = 1 # stopping the shell stops debugger
            self._break_status = end_status
            self.dbg.getInteractiveDebugger()
            self.dbg.set_continue()
            self.dbg.starttrace()

        deregisterClient(self)
        warnMainThreadEnding()
        if not self._stop:
            # we want to stop now until the IDE chooses to end the session
            while not self._detach:
                self.cmdloop()

        if self._stdin:
            sys.stdin = self._stdin.stop()
        self.dbg = None

    def getHostName(self):
        # if we're running under a webserver, get the webserver hostname
        # otherwise return the hostname normally
        if os.environ.has_key("HTTP_HOST"):
            return os.environ["HTTP_HOST"]
        return socket.gethostname()

    def _createInitAttrs(self, name, filename):
        attrs = {'xmlns': 'urn:debugger_protocol_v1',
                 'hostname': self.getHostName(),
                 'appid': self.appid,
                 'idekey': self.ide_key,
                 'thread': "%s %d" % (name, self.thread_id),
                 'parent': self.parent_appid,
                 'session': getenv('DBGP_COOKIE',''),
                 'language': 'python',
                 'protocol_version': '1.0'}

        if filename == 'interactive':
            self._break_status = STATUS_BREAK
            attrs['interactive'] = '>>> '
        else:
            filename = pathname2url(filename)
            attrs['fileuri'] = filename
        return attrs

    def sendInit(self, name, filename):
        attrs = self._createInitAttrs(name, filename)
        self.socket.send_response('<init %s/>' % _getAttrStr(attrs))

    def poll(self):
        return self.supports_async and \
            self._continue != RESUME_STOP and \
            not self.socket.queue.empty()

    def cmdloop(self, async=0):
        # loop reading commands until no more commands are avialable
        # if this is async, only do one command
        #log.debug("cmdloop async=%d", async)
        if async and not self.poll():
            return self._continue
        self._continue = RESUME_STOP

        while not self._continue and not self._detach:
            if not async and self._continueTransactionId is not None:
                self.send_continuationResult(self._continuationCommand, STATUS_BREAK, REASON_OK)
            #log.debug("retreiving current command packet")
            data = None
            while not data and not self._detach:
                # timeout in half second intervals.  Ignore the exception
                # and see if we've detached from debugging.  If so, we'll
                # fall out of here rather than blocking (and locking up)
                try:
                    data = self.socket.queue.get(1)
                    if (self.socket.queue.empty()):
                        self.dbg.interrupt = 0
                except:
                    pass

            #log.debug("cmdloop %r", data)
            if data:
                if async:
                    self.onecmd(data, 'do_async_')
                else:
                    self.onecmd(data)

            if async:
                break

        return self._continue

    def send_stream(self, cmd, data=None):
        if not data:
            return
        _template = '<stream type="%s" encoding="%s">%s</stream>'
        if self._data_encoding == 'base64':
            data = base64_encodestring(data).rstrip()
        else:
            data = escape(data)

        self.socket.send_response(_template % (cmd,self._data_encoding,data))

    def send_continuationResult(self, command, status, reason):
        if self._continueTransactionId is None:
            log.debug("no continuation transaction id")
            return

        _template = '<response xmlns="urn:debugger_protocol_v1" command="%s" status="%s" reason="%s" transaction_id="%s"%s/>'
        self._break_reason = reason
        self._break_status = status
        name = resume_command_names[command]
        reason = reason_names[reason]
        status = status_names[status]
        interactive = ""
        if self._break_status == STATUS_INTERACTIVE:
            interactive = ' prompt=">>> " more="0"'
        self.socket.send_response(_template % (name, status, reason, self._continueTransactionId, interactive))
        self._continueTransactionId = None

    def _getopts(self, args, options, cmd="unknown"):
        # options is an array of option arrays:
        # [['i','transaction_id',int,1,-1, func],...]
        # [short_arg, long_arg, type_handler, required, default, validat_func]
        # returns values for all requested options
        origargs = args
        short = ''
        longopt = []
        shortopt = []
        found = []
        for opt in options:
            short = short + opt[0]+':'
            shortopt.append('-'+opt[0])
            longopt.append(opt[1])
        try:
            opts, args = getopt.getopt(args, short, longopt)
        except getopt.GetoptError, e:
            tid = self._getTransactionId(origargs)
            raise CommandError(cmd,tid,ERROR_INVALID_ARGS,'invalid argument supplied: %s' % (str(e)))
        # get the default values
        result = [o[4] for o in options]
        # override defaults with provided arg values
        for o, a in opts:
            found.append(o)
            if o in shortopt:
                i = shortopt.index(o)
                result[i] = options[i][2](a.strip())
                if options[i][5]:
                    options[i][5](self, result[i])
            elif o in longopt:
                i = longopt.index(o)
                result[i] = options[i][2](a.strip())
                if options[i][5]:
                    options[i][5](self, result[i])
        # check for required arguments
        for o in options:
            i = options.index(o)
            if o[3] and not (shortopt[i] in found or longopt[i] in found):
                tid = self._getTransactionId(origargs)
                raise CommandError(cmd,tid,ERROR_INVALID_ARGS,'required argument [%s:%s] missing' % (o[0],o[1]))
        data = ' '.join(args)
        result.append(data)
        return result

    def _getTransactionId(self, args):
        # try to find the transaction id
        if '-i' in args:
            tid = args[args.index("-i")+1]
        elif "--transaction-id" in args:
            tid = args[args.index("--transaction-id")+1]
        else:
            tid = "-1"
        return tid

    def onecmd(self, argv, fbegin = 'do_'):
        try:
            self.lastcmd = argv
            cmd = argv[0]
            if cmd == '':
                return self.default(argv)
            else:
                try:
                    func = getattr(self, fbegin + cmd)
                except AttributeError:
                    return self.default(argv)
                return func(argv[1:])
        except CommandError, e:
            if not e.tid:
                try:
                    e.tid = self._getTransactionId(argv[1:])
                except Exception, e:
                    pass
            if cmd and e.name != cmd:
                e.name = cmd
            self.socket.send_response(str(e))
            return None
        except SystemExit, e:
            # we dont want to send anything on an exit, just reraise
            raise
        except Exception, e:
            # When things don't go as expected uncomment this line
            #log.exception("Problem in cmd:%s", cmd)
            try:
                tid = self._getTransactionId(argv[1:])
            except:
                tid = 0
            ex = CommandError(cmd, tid, ERROR_EXCEPTION, str(e))
            self.socket.send_response(str(ex))
            raise
            return None

    def default(self, argv):
        try:
            tid = self._getTransactionId(argv[1:])
        except Exception, e:
            log.exception(e)
            tid = '-1'
        self._continue = RESUME_STOP
        raise CommandError(argv[0], tid, ERROR_COMMAND_NOT_SUPPORTED,
                           'command not supported')

class backendCmd(backend):
    """DBGP Command Handler

    This class contains all the command handlers for DBGP
    """

    # application wide debugger configuration vars
    debug_threads = 0 # must turn on to debug threads
    supports_threads = 1
    language_name = 'Python'
    language_version = sys.version
    supports_async = 1
    _max_children = MAX_CHILDREN
    _max_data = MAX_DATA
    _max_depth = MAX_DEPTH
    _show_hidden = SHOW_HIDDEN

    def get_feature_language_supports_threads(self):
        return self.supports_threads

    def get_feature_language_name(self):
        return self.language_name

    def get_feature_language_version(self):
        return self.language_version

    def get_feature_encoding(self):
        return self._encoding

    def set_feature_encoding(self, value):
        import codecs
        try:
            codec = codecs.lookup(value)
            self._encoding = value
            return 1
        except LookupError, e:
            return 0

    def get_feature_data_encoding(self):
        return self._data_encoding

    def set_feature_data_encoding(self, value):
        if value == 'base64' or value == 'none':
            self._data_encoding = value
            return 1
        return 0

    def get_feature_protocol_version(self):
        return DBGP_VERSION

    def get_feature_supports_async(self):
        return self.supports_async

    def get_feature_multiple_sessions(self):
        return self.debug_threads

    def set_feature_multiple_sessions(self, value):
        self.debug_threads = long(value)
        set_thread_support(self.debug_threads)
        return 1

    def get_feature_max_children(self):
        return self._max_children

    def set_feature_max_children(self, value):
        self._max_children = long(value)
        return 1

    def get_feature_max_data(self):
        return self._max_data

    def set_feature_max_data(self, value):
        self._max_data = long(value)
        return 1

    def get_feature_max_depth(self):
        return self._max_depth

    def set_feature_max_depth(self, value):
        self._max_depth = long(value)
        return 1

    def get_feature_show_hidden(self):
        return self._show_hidden

    def set_feature_show_hidden(self, value):
        self._show_hidden = long(value)
        return 1

    def set_feature_notify_ok(self, value):
        dbgpSocket.notify_ok = long(value)
        return 1

    def get_feature_supports_postmotem(self):
        return 1

    def do_help(self, cmdargs, *args):
        _template = '<response xmlns="urn:debugger_protocol_v1" command="help" transaction_id="%s"><![CDATA[%s]]></response>'
        tid = self._getTransactionId(cmdargs)
        stdout = sys.stdout
        sys.stdout = StringIO.StringIO()
        listcmd.ListCmd.do_help(self, args)
        out = sys.stdout.getvalue()
        self.socket.send_response(_template % (tid, out))
        sys.stdout = stdout

    def do_async_status(self, cmdargs, *args):
        self.do_status(cmdargs, args)

    def do_status(self, cmdargs, *args):
        _template = '<response xmlns="urn:debugger_protocol_v1" command="status" status="%s" reason="%s" transaction_id="%s">%s</response>'
        tid = self._getTransactionId(cmdargs)
        self.socket.send_response(_template %
                            (status_names[self._break_status],
                             reason_names[self._break_reason],
                             tid,
                             self._lastErrorMessage))


    _stop_optlist = [['i', 'transaction_id', int, 1, -1, None],
                ['e', 'exit_code', int, 0, 0, None]]
    def do_async_stop(self, cmdargs, *args):
        self.do_stop(cmdargs, args)

    def do_stop(self, cmdargs, *args):
        (tid, exit, data,) = self._getopts(cmdargs, self._stop_optlist, "stop")

        _template = '<response xmlns="urn:debugger_protocol_v1" command="stop" status="stopped" reason="ok" transaction_id="%s">%s</response>'
        self.socket.send_response(_template % (tid,'application terminated'))

        self._continueTransactionId = tid
        backend._stop = 1
        self.stopNow()
        self._continue = RESUME_STOP
        if self._stdin:
            sys.stdin = self._stdin.stop()

        sys.exit(exit)

    def do_async_break(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)

        frame = sys._getframe().f_back
        self.dbg.setup(frame, None)
        self.dbg.set_step()
        self.dbg.starttrace()

        # we dont know if this will successfully break or not :(
        _template = '<response xmlns="urn:debugger_protocol_v1" command="break" transaction_id="%s" success="1"/>'
        self.socket.send_response(_template % (tid))

        self.send_continuationResult(self._continuationCommand, STATUS_BREAK, REASON_OK)

    def do_break(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)
        raise CommandError('break', tid, ERROR_COMMAND_NOT_AVAILABLE,
                           'break is only available while running')

    def do_async_detach(self, cmdargs, *args):
        self.do_detach(cmdargs, args)

    def do_detach(self, cmdargs, *args):
        _template = '<response xmlns="urn:debugger_protocol_v1" command="detach" status="stopped" reason="ok" transaction_id="%s">%s</response>'
        self._continueTransactionId = self._getTransactionId(cmdargs)
        self._continue = RESUME_GO
        self.socket.send_response(_template % (self._continueTransactionId,''))
        log.debug('do_detach send response')
        if self._stdin:
            sys.stdin = self._stdin.stop()
        self.detachNow()

    def _do_continue(self, cmd, cmdargs, state, *args):
        tid = self._getTransactionId(cmdargs)
        if self._break_status not in [STATUS_BREAK, STATUS_STARTING]:
            raise CommandError(cmd, tid, ERROR_COMMAND_NOT_AVAILABLE,
                           '%s is only available in break state' % cmd)
        self._break_status = STATUS_RUNNING
        self._continueTransactionId = tid
        self._continuationCommand = self._continue = state

    def do_run(self, cmdargs, *args):
        self._do_continue('run', cmdargs, RESUME_GO, *args)

    def do_step_into(self, cmdargs, *args):
        self._do_continue('step_into', cmdargs, RESUME_STEP_IN, *args)

    def do_step_over(self, cmdargs, *args):
        self._do_continue('step_over', cmdargs, RESUME_STEP_OVER, *args)

    def do_step_out(self, cmdargs, *args):
        self._do_continue('step_out', cmdargs, RESUME_STEP_OUT, *args)


    _feature_get_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['n', 'feature_name', str, 1, None, None]]
    def do_feature_get(self, cmdargs, *args):
        feature_value = ''
        feature_success = 0

        (tid, name, data,) = self._getopts(cmdargs, self._feature_get_optlist, "feature_get")

        if hasattr(self, 'get_feature_'+name):
            func = getattr(self, 'get_feature_'+name)
            feature_value = func()
            if feature_value:
                feature_value = '<![CDATA[%s]]>' % feature_value
            feature_success = 1
        elif hasattr(self, name+'_enabled'):
            feature_success = getattr(self, name+'_enabled')
        elif hasattr(self, 'do_'+name):
            feature_success = 1
        else:
            feature_success = 0

        _template = '<response xmlns="urn:debugger_protocol_v1" command="feature_get" feature_name="%s" supported="%d" transaction_id="%s">%s</response>'
        self.socket.send_response(_template % (name, feature_success, tid, feature_value))


    _feature_set_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['n', 'feature_name', str, 1, None, None],
               ['v', 'feature_value', str, 1, None, None]]
    def do_feature_set(self, cmdargs, *args):
        (tid, name, feature_value, data,) = \
            self._getopts(cmdargs, self._feature_set_optlist, "feature_set")
        feature_success = 0

        try:
            func = getattr(self, 'set_feature_'+name)
            feature_success = func(feature_value)
        except AttributeError:
            feature_success = 0

        _template = '<response xmlns="urn:debugger_protocol_v1" command="feature_set" feature_name="%s" success="%d" transaction_id="%s"/>'
        self.socket.send_response(_template % (name, feature_success, tid))


    def do_stack_depth(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)
        depth = len(self.dbg.stack)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="stack_depth" depth="%d" transaction_id="%s"/>'
        self.socket.send_response(_template % (depth, tid))


    stack_re = re.compile('.*?<(.*?)>.*')
    _stack_get_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['d', 'depth', int, 0, 0, _validateStackDepth]]
    def do_stack_get(self, cmdargs, *args):
        (tid, depth, data,) = self._getopts(cmdargs, self._stack_get_optlist, "stack_get")

        _frame_template = '<stack level="%d" type="%s" filename="%s" lineno="%d" where="%s"/>'
        ret = []
        level = -1
        try:
            for item in self.dbg.stack:
                level = level + 1
                (filename, lineno, where) = _get_stack_data(item)
                type = 'file'
                if filename.startswith('<'):
                    type = filename[1:-1]
                    # XXX if we figure out how to get the source from an exec
                    # statement, we can do something like this: (see do_source)
                    #filename = "dbgp:///"+self.stack_re.match(repr(item)).group(1)
                    filename = "dbgp:///"+type
                elif not filename.startswith('dbgp:'):
                    filename = pathname2url(filename)
                ret.append( _frame_template % (level, type,
                                               escape(filename),
                                               lineno, escape(where)) )
        except Exception, e:
            tb = escape(''.join(traceback.format_list(traceback.extract_tb(sys.exc_info()[2]))))
            raise CommandError('stack_get', tid, ERROR_EXCEPTION,
                               'Unknown exception %s\n%s' % (str(e), tb))

        _template = '<response xmlns="urn:debugger_protocol_v1" command="stack_get" depth="%d" transaction_id="%s">%s</response>'
        stack_depth = len(self.dbg.stack)
        if depth > 0:
            self.socket.send_response(_template % (stack_depth, tid, ret[depth]))
        else:
            self.socket.send_response(_template % (stack_depth, tid, ''.join(ret)))


    def do_context_names(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="context_names" transaction_id="%s">'
        for name in contextNames:
            _template += '<context name="%s" id="%d"/>' % (name, contextNames.index(name))
        _template += '</response>'
        self.socket.send_response(_template % tid)


    _context_get_optlist = [['i','transaction_id', int, 1, -1, None],
               ['d','depth', int, 0, 0, _validateStackDepth],
               ['c','context_id', int, 0, 0, _validateContextId]]
    def do_context_get(self, cmdargs, *args):
        (tid, depth, context_id, data,) = \
            self._getopts(cmdargs, self._context_get_optlist, "context_get")

        contextTypes = hiddenContextTypes[context_id]
        try:
            frame, lineno = self.dbg.stack[depth]
            if context_id == 0: # Locals
                items = frame.f_locals
            elif context_id < len(contextNames): # Globals
                items = frame.f_globals
            else:
                raise CommandError('context_get', tid, ERROR_CONTEXT_INVALID,
                                   'Invalid context id [%d] requested' % context_id)

            ret = []
            if _supports_keyed_sort:
                names = sorted(items.keys(), key = str.lower)
            else:
                names = items.keys()
                def mycmp(i,j): return cmp(i.lower(), j.lower())
                names.sort(mycmp)
            # Remove __builtins__ everywhere!
            if "__builtins__" in names:
                names.remove('__builtins__')

            for name in names:
                if (not self._show_hidden) and (name[:2] == name[-2:] == '__'):
                    continue
                item = items[name]
                typ = type(item)
                if contextTypes:
                    if typ not in contextTypes:
                        continue
                elif typ in HiddenTypes and name not in frame.f_code.co_varnames:
                        continue
                itemProperty = Property(name, name, item, self._data_encoding,
                                        self._show_hidden, contextTypes)

                ret.append( itemProperty.toxml(0,  self._max_children, self._max_data) )
        except Exception, e:
            tb = escape(''.join(traceback.format_list(traceback.extract_tb(sys.exc_info()[2]))))
            raise CommandError('context_get', tid, ERROR_EXCEPTION,
                               'Unknown exception %s\n%s' % (str(e),tb))

        _template = '<response xmlns="urn:debugger_protocol_v1" command="context_get" context="%d" transaction_id="%s">%s</response>'
        data = ''.join(ret)
        self.socket.send_response(_template % (context_id, tid, data))

    def _getObject(self, frame_index, expr):
        frame, lineno = self.dbg.stack[frame_index]
        try:
            value = eval(expr, frame.f_globals, frame.f_locals)
            typ = _get_object_type_string(value)
        except:
            value = _format_exception_only()
            typ = "Error"

        return value, typ

    def _getContextObject(self, context_id, frame_index, expr ):
        frame, lineno = self.dbg.stack[frame_index]
        if context_id == 0: # Locals
            bindings = frame.f_locals
        elif context_id == 1: # Globals
            bindings = frame.f_globals

        try:
            value = eval(expr, bindings)
            typ = _get_object_type_string(value)
        except Exception, e:
            #print str(e)
            value = _format_exception_only()
            typ = "Error"

        return value, typ


    _property_get_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['d', 'depth', int, 0, 0, _validateStackDepth],
               ['c', 'context_id', int, 0, 0, _validateContextId],
               ['n', 'fullname', str, 1, None, None],
               ['m', 'maxdata', int, 0, 0, None],
               ['t', 'datatype', str, 0, None, None],
               ['p', 'datapage', int, 0, 0, None]]
    def do_property_get(self, cmdargs, *args):
        (tid, depth, context_id, fullname,
         maxdata, datatype, datapage, data,) = \
            self._getopts(cmdargs, self._property_get_optlist, "property_get")

        value, typ = self._getContextObject(context_id, depth, fullname)
        if typ == 'Error':
            value, typ = self._getObject(depth, fullname)
            if typ == 'Error':
                raise CommandError('property_get', tid,
                                   ERROR_PROPERTY_DOES_NOT_EXIST, value)
        if not maxdata:
            maxdata = self._max_data

        prop = Property(fullname, fullname, value, self._data_encoding,
                            self._show_hidden, hiddenContextTypes[context_id])

        _template = '<response xmlns="urn:debugger_protocol_v1" command="property_get" context="%d" transaction_id="%s">%s</response>'

        self.socket.send_response(_template %
                           (context_id, tid,
                            prop.toxml(self._max_depth,
                                       self._max_children,
                                       maxdata,
                                       datapage)))


    _property_value_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['d', 'depth', int, 0, 0, _validateStackDepth],
               ['c', 'context_id', int, 0, 0, _validateContextId],
               ['n', 'fullname', str, 1, None, None]]
    def do_property_value(self, cmdargs, *args):
        (tid, depth, context_id, fullname, data,) = \
            self._getopts(cmdargs, self._property_value_optlist, "property_value")

        value, typ = self._getContextObject(context_id, depth, fullname)
        if typ == 'Error':
            raise CommandError('property_value', tid,
                               ERROR_PROPERTY_DOES_NOT_EXIST, value)

        prop = Property(fullname, fullname, value, self._data_encoding,
                            self._show_hidden, hiddenContextTypes[context_id])

        _template = '<response xmlns="urn:debugger_protocol_v1" command="property_value" size="%d" encoding="%s" transaction_id="%s">%s</response>'
        vType = prop.get_type()
        encoding=''
        value=''
        size=0
        if vType not in StringTypes:
            #if prop.numchildren == 0 or vType in HiddenTypes or vType == types.InstanceType:
            value = '<![CDATA[%s]]>'  % prop.get_valueString()
        else:
            value = '<![CDATA[%s]]>'  % prop.get_encodedValue()[0]
            encoding = prop.encoding
        if value:
            size = prop.get_dataSize()
        self.socket.send_response(_template % (size, encoding, tid, value))


    _property_set_optlist = [['i', 'transaction_id', int, 1, -1, None],
                   ['d', 'depth', int, 0, 0, _validateStackDepth],
                   ['c', 'context_id', int, 0, 0, _validateContextId],
                   ['n', 'fullname', str, 1, None, None],
                   ['t', 'type', str, 0, None, None],
                   ['l','length', int, 0, 0, None]]
    def do_property_set(self, cmdargs, *args):
        (tid, depth, context_id, fullname, data_type, data_length, data,) = \
            self._getopts(cmdargs, self._property_set_optlist, "property_set")
        frame, lineno = self.dbg.stack[depth]

        if self._data_encoding == 'base64':
            try:
                data = base64_decodestring(data)
            except:
                pass

        # fixup multiline strings
        if data_type:
            if data_type in ['str','unicode']:
                if data_type == 'str':
                    # no unicode data, try to downgrade the data type
                    try:
                        data = str(data)
                    except:
                        pass
                elif data_type == "unicode":
                    try:
                        data = data.decode('utf-8')
                    except (UnicodeEncodeError, UnicodeDecodeError), e:
                        try:
                            data = data.decode()
                        except (UnicodeEncodeError, UnicodeDecodeError), e:
                            pass
                data = repr(data)
                # now we can eval the string data

        # if no data type is provided, we assume that the data is an expression!!!


        # eval only evaluates the expression in the local scope, but
        # using the global scope to help with that evaluation.  We want
        # to eval the expression, but then modify the variable in the
        # correct context.  If the variable does not exist, then we
        # must use the exec statement to get it created correctly, and
        # the fetch it by the variable name.
        try:
            if frame.f_locals.has_key(fullname) \
               or frame.f_globals.has_key(fullname):
                # Eval the rhs first.
                try:
                    #print 'eval %r in %r, %r' % (data, frame.f_globals, frame.f_locals)
                    value = eval(data, frame.f_globals, frame.f_locals)
                except:
                    raise CommandError('property_set', tid,
                                       ERROR_EVAL_FAILED,
                                       'Invalid variable expression eval\'d for [%s]' % fullname)
                if context_id == 1 or \
                    (not frame.f_locals.has_key(fullname) \
                     and frame.f_globals.has_key(fullname)):
                    frame.f_globals[fullname] = value
                elif self._isInteractiveShell:
                    # we can set into locals if we're in the shell
                    # I doubt this path is ever taken. [EP - 2010-07-16]
                    frame.f_locals[fullname] = value
                elif not frame.f_code.co_varnames:
                    # We can change f_locals at top level in Python code.
                    frame.f_locals[fullname] = value
                else:
                    setlocal(frame, fullname, value)

            else:
                # Hack an assignment together.
                # XXX This doesn't always work because of LOAD_FAST.
                # Either we need to work around or change this code to
                # generate an error message if the assignment fails.

                expr = fullname + " = " + data
                expr = str(expr)

                #print 'exec %s in %s, %s' % (expr, frame.f_globals, frame.f_locals)
                try:
                    exec expr in frame.f_globals, frame.f_locals
                    #print "frame.f_globals:", frame.f_globals
                    #print "frame.f_locals:", frame.f_locals
                except:
                    raise CommandError('property_set', tid,
                                       ERROR_INVALID_EXPRESSION,
                                       'Invalid variable expression exec\'d [%s]' % expr)
                value, typ = self._getContextObject(context_id, depth, fullname)
                if typ == 'Error':
                    raise CommandError('property_set', tid,
                                       ERROR_INVALID_EXPRESSION, value)
        except Exception ,e:
            raise CommandError('property_set', tid,
                               ERROR_INVALID_EXPRESSION,
                               'Invalid variable expression exec\'d [%s]' % e)

        _template = '<response xmlns="urn:debugger_protocol_v1" command="property_set" success="1" transaction_id="%s"/>'
        self.socket.send_response(_template % (tid))

    def do_async_breakpoint_set(self, cmdargs, *args):
        self.do_breakpoint_set(cmdargs, args)

    _breakpoint_set_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['t','type', str, 1, None, _validateBreakpointType],
               ['s','state', str, 0, 'enabled', _validateBreakpointState],
               ['n','lineno', int, 0, 0, None],
               ['f','filename', str, 0, '', None],
               ['m','function', str, 0, None, None],
               ['x','exception', str, 0, None, None],
               ['c','expression', str, 0, None, None],
               ['h','hit_value', int, 0, None, None],
               ['o','hit_condition', str, 0, None, None],
               ['r','temporary', int, 0, 0, None]]
    def do_breakpoint_set(self, cmdargs, *args):
        (tid, type, state, lineno,
         filename, function, exception,
         expression, hitValue, hitCondition, temporary, data,) = self._getopts(cmdargs, self._breakpoint_set_optlist, "breakpoint_set")

        if filename:
            filename = url2pathname(filename)
        condition = None

        if type == 'line':
            if not filename:
                (filename, ln, where) = _get_stack_data(self.dbg.stack[0])
                filename = url2pathname( filename )
        elif type in ['conditional', 'watch']:
            if data:
                condition = base64_decodestring(data)
            else:
                raise CommandError('breakpoint_set', tid,
                                   ERROR_BREAKPOINT_INVALID,
                                   'Condition or Watch breakpoint without expression!')
        elif type in ['call', 'return']:
            condition = function
        elif type == 'exception':
            condition = exception

        enabled = state == 'enabled'

        try:
            bp = self.dbg.set_break(type, filename, lineno, enabled,
                                    temporary, condition, hitValue,
                                    hitCondition)
        except Exception, e:
            raise CommandError('breakpoint_set', tid,
                               ERROR_BREAKPOINT_INVALID, str(e))

        if bp.enabled:
            state = 'enabled'
        else:
            state = 'disabled'

        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_set" transaction_id="%s" ' +\
                    'id="%d" state="%s"/>'
        self.socket.send_response(_template % (tid, bp.number, state))

    def do_async_breakpoint_update(self, cmdargs, *args):
        self.do_breakpoint_update(cmdargs, args)

    _breakpoint_update_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['d','id', int, 1, 0, None],
               ['s','state', str, 0, None, _validateBreakpointState],
               ['n','lineno', int, 0, 0, None],
               ['h','hit_value', int, 0, None, None],
               ['o','hit_condition', str, 0, None, None],
               ['r','temporary', int, 0, -1, None]]
    def do_breakpoint_update(self, cmdargs, *args):
        (tid, bpid, state, lineno,
         hitValue, hitCondition, temporary, data,) = self._getopts(cmdargs, self._breakpoint_update_optlist, "breakpoint_update")

        try:
            bp = breakpointsByNumber[bpid]
        except IndexError:
            bp = None
        if not bp:
            raise CommandError('breakpoint_update', tid,
                               ERROR_BREAKPOINT_DOES_NOT_EXIST,
                               'Breakpoint number (%d) out of range' % bpid)

        if not lineno:
            # we have to remove the old breakpoint and add it again,
            # since the breakpoints are indexed by line
            lineno = bp.line

        if not state:
            enabled = bp.enabled
        else:
            enabled = state == 'enabled'

        if temporary < 0:
            temporary = bp.temporary

        try:
            bpnew = self.dbg.set_break(bp.type, bp.file, lineno, enabled,
                                    temporary, bp.cond, hitValue,
                                    hitCondition)

            # XXX TODO make this part of our breakpoint class

            # remove the old, reset the id
            bp.deleteMe()
            bp = copy.copy(bpnew)
            bp.number = bpid
            bpnew.deleteMe()
            bp.insert()
        except Exception, e:
            raise CommandError('breakpoint_update', tid,
                               ERROR_BREAKPOINT_INVALID, str(e))

        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_update" transaction_id="%s"/>'
        self.socket.send_response(_template % (tid))

    def do_async_breakpoint_get(self, cmdargs, *args):
        self.do_breakpoint_get(cmdargs, args)

    _breakpoint_info_optlist = \
        [['i','transaction_id', int, 1, -1, None],
        ['d','id', int, 1, 0, None]]
    def do_breakpoint_get(self, cmdargs, *args):
        (tid, bpid, data,) = self._getopts(cmdargs, self._breakpoint_info_optlist, "breakpoint_get")

        try:
            bp = breakpointsByNumber[bpid]
        except IndexError:
            bp = None
        if not bp:
            raise CommandError('breakpoint_get', tid,
                               ERROR_BREAKPOINT_DOES_NOT_EXIST,
                               'Breakpoint number (%d) out of range' % bpid)
        bpinfo = bp.toxml()
        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_get" transaction_id="%s">%s</response>'
        self.socket.send_response(_template % (tid, bpinfo))

    def do_async_breakpoint_enable(self, cmdargs, *args):
        self.do_breakpoint_enable(cmdargs, args)

    def do_breakpoint_enable(self, cmdargs, *args):
        (tid, bpid, data,) = self._getopts(cmdargs, self._breakpoint_info_optlist, "breakpoint_enable")

        try:
            bp = breakpointsByNumber[bpid]
        except IndexError:
            bp = None
        if not bp:
            raise CommandError('breakpoint_set', tid,
                               ERROR_BREAKPOINT_DOES_NOT_EXIST,
                               'Breakpoint number (%d) out of range' % bpid)

        bp.enable()
        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_enable" transaction_id="%s" ' +\
                    'id="%d" state="enabled"/>'
        self.socket.send_response(_template % (tid, bpid))

    def do_async_breakpoint_disable(self, cmdargs, *args):
        self.do_breakpoint_disable(cmdargs, args)

    def do_breakpoint_disable(self, cmdargs, *args):
        (tid, bpid, data,) = self._getopts(cmdargs, self._breakpoint_info_optlist, "breakpoint_disable")

        try:
            bp = breakpointsByNumber[bpid]
        except IndexError:
            bp = None
        if not bp:
            raise CommandError('breakpoint_disable', tid,
                               ERROR_BREAKPOINT_DOES_NOT_EXIST,
                               'Breakpoint number (%d) out of range' % bpid)

        bp.disable()
        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_disable" transaction_id="%s" ' +\
                    'id="%d" state="disabled"/>'
        self.socket.send_response(_template % (tid, bpid))

    def do_async_breakpoint_remove(self, cmdargs, *args):
        self.do_breakpoint_remove(cmdargs, args)

    def do_breakpoint_remove(self, cmdargs, *args):
        (tid, bpid, data,) = self._getopts(cmdargs, self._breakpoint_info_optlist, "breakpoint_remove")

        try:
            bp = breakpointsByNumber[bpid]
        except IndexError:
            bp = None
        if not bp:
            raise CommandError('breakpoint_remove', tid,
                               ERROR_BREAKPOINT_DOES_NOT_EXIST,
                               'Breakpoint number (%d) out of range' % bpid)

        bp.deleteMe()
        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_remove" transaction_id="%s"/>'
        self.socket.send_response(_template % tid)

    def do_async_breakpoint_list(self, cmdargs, *args):
        self.do_breakpoint_list(cmdargs, args)

    def do_breakpoint_list(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)

        bpinfo = []
        for bp in breakpointsByNumber:
            # seems bpbynumber always has a single item == None
            if not bp:
                continue
            bpinfo.append(bp.toxml())
        bpinfo = ''.join(bpinfo)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="breakpoint_list" transaction_id="%s">%s</response>'
        self.socket.send_response(_template % (tid, bpinfo))

    _eval_optlist = [['i','transaction_id', int, 1, -1, None]]
    # _eval_optlist = [['i','transaction_id', int, 1, -1, None],
                # ['l','length', int, 1, 0, None]]
    def do_eval(self, cmdargs, *args):
        (tid, data,) = self._getopts(cmdargs, self._eval_optlist, "eval")
        # (tid, data_length, data,) = self._getopts(cmdargs, self._eval_optlist, "eval")

        # read data_length from the socket
        if self._data_encoding == 'base64':
            try:
                data = base64_decodestring(data)
            except:
                pass
        data = data + "\n"
        frame, lineno = self.dbg.stack[0]
        try:
            value = eval(data, frame.f_globals, frame.f_locals)
        except Exception, e:
            raise CommandError('eval', tid, ERROR_EVAL_FAILED,
                           'eval of expression failed: '+str(e))

        prop = Property(data,data, value, self._data_encoding,
                            self._show_hidden, hiddenContextTypes[0])
        # prop = Property(None, None, value, self._data_encoding,
                            # self._show_hidden, hiddenContextTypes[context_id])

        _template = '<response xmlns="urn:debugger_protocol_v1" command="eval" transaction_id="%s">%s</response>'

        self.socket.send_response(_template %
                           (tid,
                            prop.toxml(self._max_depth,
                                       self._max_children,
                                       self._max_data,
                                       0)))

    _source_optlist = [['i', 'transaction_id', int, 1, -1, None],
               ['f','filename', str, 0, None, None],
               ['b','startline', int, 0, 0, None],
               ['e','endline', int, 0, -1, None]]
    def do_source(self, cmdargs, *args):
        (tid, filename, startline, endline, data,) = \
            self._getopts(cmdargs, self._source_optlist, "source")
        source = None
        if not filename:
            (filename, lineno, where) = _get_stack_data(self.dbg.stack[0])

        try:
            filepath = url2pathname( filename )
            fullpath = pathname2url( filepath )
            f = open(filepath)
            source = f.readlines()
            f.close()
        except IOError, e:
            if filename.startswith("dbgp:"):
                source = ["Source for exec/eval is unavailable"]

                # XXX if we figure out how to get the source from an exec
                # statement, we can do something like this:
                #filename = filename[8:]
                #for item in self.dbg.stack:
                #    m = self.stack_re.match(repr(item))
                #    if m and m.group(1) == filename:
                #        source = ["Source Unavailable"]
                #        break
                #if not source:
                #    raise CommandError('source', tid,
                #               ERROR_FILE_ACCESS,
                #               'source not available %s\n%s' % (filename,str(e)))
            else:
                raise CommandError('source', tid,
                               ERROR_FILE_ACCESS,
                               'invalid file uri %s\n%s' % (filename,str(e)))

        if startline > 0 or endline > -1:
            source = ''.join(source[startline:endline])
        else:
            source = ''.join(source)

        if self._data_encoding == 'base64':
            source = base64_encodestring(source)
        else:
            source = escape(source)


        _template = '<response xmlns="urn:debugger_protocol_v1" command="source" transaction_id="%s" ' +\
                    'filename="%s" startline="%d" endline="%d" ' +\
                    'encoding="%s"><![CDATA[%s]]></response>'
        self.socket.send_response(_template % (tid, fullpath, startline,
                                        endline, self._data_encoding,
                                        source))

    def do_async_stdin(self, cmdargs, *args):
        self.do_stdin(cmdargs, args)

    _stdin_optlist = [['i','transaction_id', int, 1, -1, None],
                ['c','type', int, 0, None, None]]
    def do_stdin(self, cmdargs, *args):
        (tid, copy, data,) = \
            self._getopts(cmdargs, self._stdin_optlist, "stdin")

        if copy is not None:
            if copy and not self._stdin:
                sys.stdin = self._stdin = StreamIn(sys.stdin, self)
            elif not copy and self._stdin:
                sys.stdin = self._stdin.stop()
                sys.stdin.close()
                self._stdin = None
            else:
                raise CommandError('stdin', tid,
                               ERROR_STREAM_REDIRECT_FAILED,
                               'setting stdin redirection failed')
        elif self._stdin:
            # read data_length from the socket
            try:
                data = base64_decodestring(data)
            except:
                pass
            if data:
                sys.stdin.write(data)
            else:
                sys.stdin = self._stdin.stop()
                sys.stdin.close()
                self._stdin = None
        else:
            # we got stdin data without a request to redirect stdin
            raise CommandError('stdin', tid,
                               ERROR_STREAM_REDIRECT_FAILED,
                               'invalid stdin access, redirect first')

        # send a response
        _template = '<response xmlns="urn:debugger_protocol_v1" command="stdin" success="1" transaction_id="%s"/>'
        self.socket.send_response(_template % tid)

    _redirect_optlist = [['i','transaction_id', int, 1, -1, None],
               ['c','type', int, 0, 1, None]]
    def do_stdout(self, cmdargs, *args):
        (tid, copy, data,) = \
            self._getopts(cmdargs, self._redirect_optlist, "stdout")
        if self._stdout:
            if copy:
                raise CommandError('stdout', tid,
                                   ERROR_STREAM_REDIRECT_FAILED,
                                   'Already redirected')
            sys.stdout = self._stdout.stop()
            self._stdout = None
        else:
            sys.stdout = self._stdout = StreamOut('stdout', sys.stdout, self, copy==2)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="stdout" success="1" transaction_id="%s"/>'
        self.socket.send_response(_template % tid)

    def do_stderr(self, cmdargs, *args):
        (tid, copy, data,) = \
            self._getopts(cmdargs, self._redirect_optlist, "stderr")
        if self._stderr:
            if copy:
                raise CommandError('stderr', tid,
                                   ERROR_STREAM_REDIRECT_FAILED,
                                   'Already redirected')
            sys.stderr = self._stderr.stop()
            self._stderr = None
        else:
            sys.stderr = self._stderr = StreamOut('stderr', sys.stderr, self, copy==2)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="stderr" success="1" transaction_id="%s"/>'
        self.socket.send_response(_template % tid)

    def do_typemap_get(self, cmdargs, *args):
        tid = self._getTransactionId(cmdargs)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="typemap_get" transaction_id="%s" ' + \
                    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' + \
                    'xmlns:xsd="http://www.w3.org/2001/XMLSchema" ' + \
                    '>%s</response>'
        _map = '<map type="%s" name="%s"%s/>'
        if _is_py3:
            objectIndex = object
        else:
            objectIndex = types.InstanceType
        commonTypes = {
            types.IntType:      ['int',' xsi:type="xsd:int"'],
            types.LongType:     ['int',' xsi:type="xsd:long"'],
            types.FloatType:    ['float',' xsi:type="xsd:float"'],
            types.StringType:   ['string',' xsi:type="xsd:string"'],
            types.NoneType:     ['null',''],
            types.ListType:     ['array',''],
            types.TupleType:    ['array',''],
            types.DictType:     ['hash',''],
            objectIndex:        ['object',''],
        }
        if hasattr(types,'BooleanType'):
            commonTypes[types.BooleanType] = ['bool',' xsi:type="xsd:boolean"']
        if hasattr(types,'UnicodeType'):
            commonTypes[types.UnicodeType] = ['string',' xsi:type="xsd:string"']

        # a better way to do this?
        # make a list of all the types defined above, then put all the
        # other types into the 'resource' type

        map = []
        usedTypes = []
        for pyType in commonTypes.keys():
            commonTypeName = commonTypes[pyType][0]
            schemaType = commonTypes[pyType][1]
            map.append(_map % (commonTypeName,
                               pyType.__name__,
                               schemaType))
            usedTypes.append(pyType.__name__)

        for pyTypeAttr in dir(types):
            pyType = getattr(types,pyTypeAttr)
            if type(pyType) == types.TypeType and \
                pyType.__name__ not in usedTypes:
                map.append(_map % ('resource',pyType.__name__,''))
                usedTypes.append(pyType.__name__)

        maps = ''.join(map)
        self.socket.send_response(_template % (tid,maps))

    _interact_optlist = [['i','transaction_id', int, 1, -1, None],
                         ['m','mode', int, 0, 1, None]]
    def do_interact(self, cmdargs, *args):

        (tid, mode, data,) = \
            self._getopts(cmdargs, self._interact_optlist, "interact")

        lastStatus = self._break_status
        self._break_status = STATUS_INTERACTIVE

        prompt = ">>> "
        more = 0
        status = "interactive"
        if not mode:
            # we're stopping the interactive session
            self._interactiveBuffer = []
            prompt = ""
            status = "break"
            self._break_status = STATUS_BREAK
            self.dbg.releaseInteractiveDebugger()
            if self._isInteractiveShell:
                # if we quit interacting, then quit the shell too
                self.stopNow()
                self._break_status = STATUS_STOPPED
                status = "stopped"
        elif data or self._interactiveBuffer:
            try:
                data = base64_decodestring(data)
            except:
                pass
            if data.strip() == "" and len(self._interactiveBuffer) and \
                self._interactiveBuffer[-1].strip() == "":
                # dedent on a second blank line
                data = ""

            data = data.split('\n')
            for line in data:
                self._interactiveBuffer.append(line)
                source = '\n'.join(self._interactiveBuffer)

                more = self.dbg.getInteractiveDebugger().runsource(source, '<console>')
                if more:
                    prompt = "... "
                else:
                    self._interactiveBuffer = []

        self._break_status = lastStatus
        _template = '<response xmlns="urn:debugger_protocol_v1" command="interact" status="%s" more="%d" prompt="%s" transaction_id="%s"/>'
        self.socket.send_response(_template % (status, more, prompt, tid))


class codeProfilingCmd(backendCmd):
    """DBGP Code Profiling Handler

    This class contains all the command handlers for DBGP code profiling.
    """

    def setProfileData(self, rawprofdata):
        self.rawprofdata = rawprofdata

    def _createInitAttrs(self, name, filename):
        """Override backendCmd to add the type information."""
        attrs = backendCmd._createInitAttrs(self, name, filename)
        attrs['type'] = "code_profiling"
        return attrs

    _profile_data_optlist = [['i', 'transaction_id', int, 1, -1, None]]
    def do_profile_data(self, cmdargs, *args):
        (tid, data,) = self._getopts(cmdargs, self._profile_data_optlist, "profile_data")

        encoded_profile_data = base64_encodestring(self.rawprofdata)
        _template = '<response xmlns="urn:debugger_protocol_v1" command="profile_data" transaction_id="%s" ' +\
                              'encoding="base64"><![CDATA[%s]]></response>'
        self.socket.send_response(_template % (tid, encoded_profile_data))


import code

# code module rudely doesn't export this
def softspace(file, newvalue):
    oldvalue = 0
    try:
        oldvalue = file.softspace
    except AttributeError:
        pass
    try:
        file.softspace = newvalue
    except (AttributeError, TypeError):
        # "attribute-less object" or "read-only attributes"
        pass
    return oldvalue


class FakeCode:
    def __init__(self, filename="<console>", co_name="__console__"):
        # number of arguments (not including * or ** args)
        self.co_argcount = 0
        # string of raw compiled bytecode
        self.co_code = ""
        # tuple of constants used in the bytecode
        self.co_consts = ()
        # name of file in which this code object was created
        self.co_filename = filename
        # number of first line in Python source code
        self.co_firstlineno = 0
        # bitmap: 1=optimized | 2=newlocals | 4=*arg | 8=**arg
        self.co_flags = 2
        # encoded mapping of line numbers to bytecode indices
        self.co_lnotab = {}
        # name with which this code object was defined
        self.co_name = co_name
        # tuple of names of local variables
        self.co_names = ()
        # number of local variables
        self.co_nlocals = 0
        # virtual machine stack space required
        self.co_stacksize = 0
        # tuple of names of arguments and local variables
        self.co_varnames = ()

class FakeFrame:
    def __init__(self, globals=None, locals=None):
        m = None
        if not globals:
            m = h_main()
            m.importSite()
            globals = m.globals
            globals["__name__"]= "__console__"
            globals["__doc__"]= None
            globals["__file__"]= "<console>"
        if not locals:
            locals = globals
        exec "import site\n\n" in globals, locals
        del globals['site']

        #next outer frame object (this frame's caller)
        self.f_back = None
        # built-in namespace seen by this frame
        self.f_builtins = None
        # code object being executed in this frame
        self.f_code = FakeCode()
        # traceback if raised in this frame, or None
        self.f_exc_traceback = None
        # exception type if raised in this frame, or None
        self.f_exc_type = None
        # exception value if raised in this frame, or None
        self.f_exc_value = None
        # global namespace seen by this frame
        self.f_globals = globals
        # index of last attempted instruction in bytecode
        self.f_lasti = 0
        # current line number in Python source code
        self.f_lineno = 0
        # local namespace seen by this frame
        self.f_locals = locals
        # 0 or 1 if frame is in restricted execution mode
        self.f_restricted = 0
        # tracing function for this frame, or None
        self.f_trace = None

class InteractiveDebugger(code.InteractiveInterpreter):

    def __init__(self, debugger, frame=None):
        """Constructor.

        The optional 'locals' argument specifies the dictionary in
        which code will be executed; it defaults to a newly created
        dictionary with key "__name__" set to "__console__" and key
        "__doc__" set to None.

        """
        self.debugger = debugger
        if not frame:
            frame = FakeFrame()
        self.frame = frame
        code.InteractiveInterpreter.__init__(self, frame.f_locals)

    def runcode(self, code):
        try:
            self.debugger.runcode(code, globals = self.frame.f_globals,
                                        locals = self.frame.f_locals)
        except SystemExit:
            raise
        except:
            _print_exc()
        else:
            if softspace(sys.stdout, 0):
                print


def _dbgp_start_new_thread(function, args=(), kwargs={}):
    # this is called after a REAL thread has been started.  Now we must
    # actually run the code that was requested for this thread.

    # try to get a name for the function that is being executed.  First, if
    # there is a class with a getName method (ie. trheading.Thread) call that,
    # second, if func_name exists, use that, otherwise repr the function
    _f_dict = dir(function)
    if 'im_self' in _f_dict and function.im_self and \
        'getName' in dir(function.im_self):
        name = function.im_self.getName()
    elif 'func_name' in _f_dict:
        name = function.func_name
    else:
        name = repr(function)

    client = backendCmd()
    ## the values for host and port do not matter here, they are retrieved
    ## appropriately from the class variables
    client.connect('', 9000, name)
    client.runThread(function, args, kwargs)

def _thread_start_new_thread(function, args=(), kwargs={}):
    # this is called prior to a REAL thread being started.  We interrupt and
    # redirect the new thread to our own function so we can connect to the
    # IDE, then run the thread under the debugger.  We call the original
    # thread.start_new_thread function here, as that is what actually creates
    # the new thread.
    return thread._thread_start_new_thread(_dbgp_start_new_thread, (function, args), kwargs)

def set_thread_support(debug_threads):
    # lib2to3.py doesn't catch instances of imports inside functions
    if sys.version_info[0] >= 3:
        import _thread
    else:
        import thread as _thread
    import threading
    if debug_threads:
        if not hasattr(_thread, '_thread_start_new_thread'):
            _thread._thread_start_new_thread = _thread.start_new_thread
            _thread.start_new_thread = _thread_start_new_thread
            threading._start_new_thread = _thread_start_new_thread
    else:
        if hasattr(_thread, '_thread_start_new_thread'):
            _thread.start_new_thread = _thread._thread_start_new_thread
            threading._start_new_thread = _thread.start_new_thread
            del _thread._thread_start_new_thread

def stopDBGP(client):
    log.debug("stopDBGP: atexit has been called")
    # prevent stepping into functions we call
    global DBGPHideChildren
    origDBGPHideChildren = DBGPHideChildren
    DBGPHideChildren = DBGPDebugDebugger is not DBGP_STOPPABLE_ALWAYS
    try:
        client.atexit()
    finally:
        DBGPHideChildren = origDBGPHideChildren

_connectionData = None
def brk(host = '127.0.0.1', port = 9000, idekey = '',
        preloadScript = None, logLevel = logging.WARN):
    global _connectionData
    # prevent stepping into functions we call
    global DBGPHideChildren
    origDBGPHideChildren = DBGPHideChildren
    DBGPHideChildren = DBGPDebugDebugger is not DBGP_STOPPABLE_ALWAYS
    try:
        client = getClientForThread()
        if client:
            # we're already connected on this thread, so just break
            client.breakNow()
            return
        if _connectionData:
            host = _connectionData['host']
            port = _connectionData['port']
            idekey = _connectionData['idekey']
            preloadScript = _connectionData['preloadScript']
            logLevel = _connectionData['logLevel']
            module = _connectionData['module']
        else:
            if not idekey:
                idekey = getenv('USER', getenv('USERNAME',''))
            module = None
            # set connectionData now
            _connectionData = {'host':host, 'port':port, 'idekey':idekey,
                              'preloadScript': preloadScript, 'logLevel': logLevel,
                              'module': module}

        # we're not connected, so lets connect now.  Also catch exit so we can end
        # the connection later
        configureLogging(log, logLevel)

        frame = sys._getframe().f_back

        # get the filename we were called from
        scriptArgs = [_filename_from_frame(frame)]
        # Note: __name__ is not always set, such as when "exec()" was used:
        #       http://bugs.python.org/issue2903
        name = frame.f_globals.get('__name__', '<unknown>')
        # set the thread debugging support now
        set_thread_support(backendCmd.debug_threads)

        # start debugging now
        client = backendCmd(idekey, preloadScript,module=module)
        client.connect(host, port, name, scriptArgs)
        import atexit
        atexit.register(stopDBGP, client)
        client.breakNow()
    finally:
        DBGPHideChildren = origDBGPHideChildren

_orig_excepthook = None
def excepthook(type, value, tb):
    # prevent stepping into functions we call
    global _connectionData
    global _orig_excepthook

    sys.excepthook = _orig_excepthook

    global DBGPHideChildren
    origDBGPHideChildren = DBGPHideChildren
    DBGPHideChildren = DBGPDebugDebugger is not DBGP_STOPPABLE_ALWAYS
    try:
        # we print the traceback to the regular stdout, since we don't know if or
        # when the IDE will redirect stdin so it can receive the traceback
        _print_exception(type, value, tb)

        client = getClientForThread()
        if client:
            # we're already connected on this thread, so let it go
            return

        # we're not connected, so lets connect now.  Also catch exit so we can end
        # the connection later

        configureLogging(log, _connectionData['logLevel'])

        frame = tb.tb_frame

        # get the filename we were called from
        scriptArgs = [_filename_from_frame(frame)]
        name = frame.f_globals['__name__']

        # start debugging now
        client = backendCmd(_connectionData['idekey'],
                            _connectionData['preloadScript'],
                            module=_connectionData['module'])
        client.connect(_connectionData['host'], _connectionData['port'], name, scriptArgs)
        client.runExceptHook(type, value, tb)
    finally:
        DBGPHideChildren = origDBGPHideChildren
    sys.exit(1)

def brkOnExcept(host = '127.0.0.1', port = 9000, idekey = '',
                preloadScript = None, logLevel = logging.WARN,
                module=None):
    global _connectionData
    global _orig_excepthook

    if not _connectionData:
        if not idekey:
            idekey = getenv('USER', getenv('USERNAME',''))

        _connectionData = {'host':host, 'port':port, 'idekey':idekey,
                              'preloadScript': preloadScript, 'logLevel': logLevel,
                              'module': module}

    _orig_excepthook = sys.excepthook
    sys.excepthook = excepthook

def runWithoutDebug(debug_args, interactive, host = '127.0.0.1', port = 9000,
                    idekey = '', logLevel = logging.WARN):
    global _connectionData

    # execute the script
    main = h_main()

    if not idekey:
        idekey = getenv('USER', getenv('USERNAME',''))
    _connectionData = {'host':host, 'port':port, 'idekey':idekey,
                          'preloadScript': None, 'logLevel': logLevel,
                          'module': main}

    try:
        # setup the exception handler
        brkOnExcept(host, port, idekey, None, logLevel, module=main)
        #exec code_ob in globals, locals
        h_execfile(debug_args[0], debug_args, module=main)
    except SystemExit, e:
        # if someone does a sys.exit(), it's not really an exception.
        pass

    # turn off exception catch
    sys.excepthook = _orig_excepthook
    if interactive:
        set_thread_support(backendCmd.debug_threads)
        client = backendCmd(idekey, module=main)
        client.connect(host, port, '__main__', debug_args)
        # wait until exit
        try:
            client.runInteractive()
        except SystemExit, e:
            # if someone does a sys.exit(), it's not really an exception.
            pass
        except:
            client.close()
            traceback.print_exc()

def runWithProfiling(debug_args, host='127.0.0.1', port=9000,
                     idekey='', logLevel=logging.WARN):
    global _connectionData

    try:
        from cProfile import Profile
    except ImportError:
        # Fallback to the pure python profiler... much slower.
        from profile import Profile

    # execute the script
    main = h_main()

    rawprofdata = None
    prof = Profile()
    try:
        try:
            h_execfile(debug_args[0], debug_args, module=main, profiler=prof)
        except SystemExit:
            # if someone does a sys.exit(), it's not really an exception.
            pass
    finally:
        # Must create the stats first.
        prof.create_stats()
        # We use cPickle for the data format, whilst the Python stdlib stats
        # module uses marshal. This is because the marshal format is insecure
        # and could be maliciously used.
        from cPickle import dumps
        # We must use pickle protocol v2 - as that is highest supported by
        # Python 2 - bug 93345.
        rawprofdata = dumps(prof.stats, protocol=2)

    if rawprofdata is not None:
        print "Program has finished, now sending code profiling data to Komodo..."
        if not idekey:
            idekey = getenv('USER', getenv('USERNAME',''))
        _connectionData = {'host':host, 'port':port, 'idekey':idekey,
                           'preloadScript': None, 'logLevel': logLevel,
                           'module': main}
        client = codeProfilingCmd(idekey, module=main)
        client.setProfileData(rawprofdata)
        # What happens now is that we initialize with Komodo, then Komodo will
        # call back asking for the profiling data - once we respond with that
        # then Komodo will close done the session.
        client.connect(host, port, '__main__', debug_args)
        client.cmdloop()
        print "Done."

