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

"""DBGP Server API module.

Generally this builds upon the lower-level dbgp.serverBase module to provide
a full module interface for a DBGP server. This module interface can be
used to provide a command-line or GUI debugger interface using the DBGP
protocol.
"""

import os
import sys
import socket, string, base64, urllib
import threading
import types
from xml.dom import minidom
import copy

try:
    import logging
except ImportError:
    from dbgp import _logging as logging
import dbgp.listcmd as listcmd

import dbgp.serverBase
from dbgp.common import *

#XXX Try to avoid dependence on PyXPCOM infrastructure in this file.
try:
    from xpcom import COMException, ServerException
except ImportError:
    COMException = ServerException = None


#---- globals
log = logging.getLogger("dbgp.server")
#log.setLevel(logging.DEBUG)
proplog = logging.getLogger("dbgp.property")
#proplog.setLevel(logging.DEBUG)
bplog = logging.getLogger("dbgp.breakpoints")
#bplog.setLevel(logging.DEBUG)


#---- internal support routines

#Note: this is not prefixed with "_" because it is being used in koDBGP.py.
def getErrorInfo(ex):
    """Given a DBGPError exception return (errno, errmsg).
    
    This is a separate method because (1) the assignment of args to DBGPError
    is not consistent and (2) the exception may also be an XPCOM COMException,
    in which case error info is expected to be on koILastErrorService.
    """
    if isinstance(ex, DBGPError):
        #XXX _Try_ to get the error message out of the DBGPError. There
        #   is no good standard for DBGPError args right now though,
        #   hence the pain here.
        if len(ex.args) == 2: # typically this is (errmsg, errno)
            errmsg = ex.args[0]
            try:
                errno = int(ex.args[1]) # sometimes this is a string
            except ValueError:
                errno = 0
        elif len(ex.args) == 1 and not hasattr(ex.args[0], "__len__"):
            # bug94837: if we're hovering over an unevaluate-able string,
            # we only get the numeric code in ex.args, so pull the message
            # out of ex.msg
            try:
                errmsg = ex.msg
                errno = ex.args[0]
            except:
                pass
        else:
            errmsg = ex.args[0]
            errno = 0
    elif isinstance(ex, COMException):
        from xpcom import components
        lastErrorSvc = components.classes["@activestate.com/koLastErrorService;1"].\
                       getService(components.interfaces.koILastErrorService)
        errno, errmsg = lastErrorSvc.getLastError()    
    return (errno, errmsg)


#---- DBGP server class hierarchy

class dataType:
    def __init__(self):
        self.commonType = '';
        self.languageType = '';
        self.schemaType = '';
    
    def initWithNode(self, node):
        self.commonType = node.getAttribute('type')
        self.languageType = node.getAttribute('name')
        if node.hasAttribute('xsi:type'):
            self.schemaType = node.getAttribute('xsi:type')
    
    def __repr__(self):
        return "%s:%s:%s" % (self.commonType, self.languageType, self.schemaType)


class breakpoint:
    """A DBGP Breakpoint.
    
    Mostly this is a "dumb" object that just holds the relevant breakpoint
    attributes. It knows how to update and clone itself, but not much more.
    """
    # List of data attributes relevant for persistence and updating.
    # Note: This last must be kept in sync with the DBGP breakpoint spec.
    _attrs = ["language", "type", "filename", "lineno", "functionName",
              "state", "hitCount", "hitValue", "hitCondition", "temporary",
              "exceptionName", "expression"]

    def __init__(self):
        # Core breakpoint attributes. These should only be modified either
        #   (1) by initializing via one of the .init*() methods; or
        #   (2) via the breakpointManager.
        self.language = ''
        self.type = ''
        self.filename = ''
        self.lineno = -1
        self.functionName = ''
        self.state = 'enabled'
        self.exceptionName = ''
        self.expression = ''
        self.temporary = 0
        self.hitCount = 0
        self.hitValue = 0
        self.hitCondition = None

        # A unique breakpoint id (a number) that is assigned and controlled
        # by the breakpointManager.
        # Note: This is not just called "id" to avoid confusion with the
        #       breakpoint id's assigned by each session.
        # Note: While called a "guid", this is NOT one of those long COM
        #       GUID strings, e.g. {5F7CB810-0AC8-4BBD-B8C1-8470E516EDBC}.
        self._guid = None
        
        # the breakpoint id as set by the debugger engine
        self._bpid = None

    def getGuid(self):
        return self._guid

    def clone(self):
        """Return a copy of this breakpoint.
        
        This is required for proper updating of a breakpoint via
        breakpointUpdate.
        """
        return copy.copy(self)

    def update(self, bp):
        """Update with the given breakpoint data and return a list of
        changed attributes.
        """
        attrNames = []
        for attrName in self._attrs:
            try:
                oldValue = getattr(self, attrName)
            except Exception, ex:
                log.error("failed to get old value of '%s' attribute: %s",
                          attrName, ex)
                raise
            try:
                newValue = getattr(bp, attrName)
            except Exception, ex:
                log.error("failed to get new value of '%s' attribute: %s",
                          attrName, ex)
                raise
            if newValue != oldValue:
                attrNames.append(attrName)
                try:
                    setattr(self, attrName, newValue)
                except Exception, ex:
                    log.error("update of '%s' attribute to '%s' failed: %s",
                              attrName, newValue, ex)
                    raise
        return attrNames

    def getName(self):
        if self.type == "line":
            name = "%s, line %s" % (os.path.basename(self.filename), self.lineno)
        elif self.type in ["conditional", "watch"]:
            name = "'%s' watched" % self.expression
            if self.filename:
                name += " in %s" % os.path.basename(self.filename)
            if self.lineno >= 1:
                name += ", line %s" % self.lineno
        elif self.type in ["call", "return"]:
            name = "%s %s" % (self.functionName, self.type)
            if self.filename:
                name += " in %s" % os.path.basename(self.filename)
        elif self.type == "exception":
            name = "Exception %s" % self.exceptionName
            if self.filename:
                name += " in %s" % os.path.basename(self.filename)
        else:
            log.error("unknown breakpoint type: '%s'" % self.type)
            name = "???"
        return name

    #---- Breakpoint initialization methods.
    def initConditional(self, lang, cond, file, line, state, temporary=None,
                        hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'conditional'
        self.filename = file
        self.lineno = line
        self.state = state
        self.expression = cond
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initWatch(self, lang, watch, file, line, state, temporary=None,
                        hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'watch'
        self.filename = file
        self.lineno = line
        self.state = state
        self.expression = watch
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initLine(self, lang, file, line, state, temporary=None,
                 hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'line'
        self.filename = file
        self.lineno = line
        self.state = state
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initException(self, lang, exceptionName, state, temporary=None,
                      hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'exception'
        self.state = state
        self.exceptionName = exceptionName
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initCall(self, lang, func, filename, state, temporary=None,
                 hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'call'
        self.filename = filename
        self.functionName = func
        self.state = state
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initReturn(self, lang, func, filename, state, temporary=None,
                   hitValue=None, hitCondition=None):
        self.language = lang
        self.type = 'return'
        self.filename = filename
        self.functionName = func
        self.state = state
        self.temporary = temporary
        self.hitValue = hitValue
        self.hitCondition = hitCondition

    def initWithNode(self, node):
        # id="%d" type="%s" filename="%s" lineno="%d" function="%s"
        # state="%s" exception="%s"
        # expression is a child element with name of expression
        self.type = node.getAttribute('type')
        if node.hasAttribute('id'):
            self._bpid = node.getAttribute('id')
        if node.hasAttribute('filename'):
            self.filename = node.getAttribute('filename')
        if node.hasAttribute('lineno'):
            self.lineno = int(node.getAttribute('lineno'))
        if node.hasAttribute('function'):
            self.functionName = node.getAttribute('function')
        if node.hasAttribute('state'):
            self.state = node.getAttribute('state')
        if node.hasAttribute('exception'):
            self.exceptionName = node.getAttribute('exception')
        if node.hasAttribute('temporary'):
            self.temporary = int(node.getAttribute('temporary'))
        if node.hasAttribute('hit_count'):
            self.hitCount = int(node.getAttribute('hit_count'))
        if node.hasAttribute('hit_value'):
            self.hitValue = int(node.getAttribute('hit_value'))
        if node.hasAttribute('hit_condition'):
            self.hitCondition = node.getAttribute('hit_condition')
        if self.type == 'expression':
            try:
                self.expression = base64.decodestring(node.firstChild.firstChild.nodeValue)
            except:
                self.expression = node.firstChild.firstChild.nodeValue
    
    def __repr__(self):
        data = ("type:%(type)s filename:%(filename)s "
                "lineno:%(lineno)s function:%(functionName)s state:%(state)s "
                "exception:%(exceptionName)s expression:%(expression)s "
                "temporary:%(temporary)s hit_count:%(hitCount)s "
                "hit_value:%(hitValue)s hit_condition:%(hitCondition)s"
                % self.__dict__)
        return "<%s: %s>" % (self.__class__, data)

    def getSetArgs(self):
        """Return a list of options for a 'breakpoint_set' command."""
        args = ['-t', self.type]
        data = None
        
        if self.filename:
            filename = self.filename
            if filename[8:].startswith('file:/'):
                filename = self.filename[8:]
            args += ['-f', filename]
        if self.type == 'line':
            args += ['-n', self.lineno]
        elif self.type in ['call', 'return']:
            args += ['-m', self.functionName]
        elif self.type == 'exception':
            args += ['-x', self.exceptionName]
        elif self.type in ['conditional', 'watch']:
            if self.lineno:
                args += ['-n', self.lineno]
            data = self.expression
        else:
            raise DBGPError('breakpoint type [%s] not supported' % self.type)

        if self.state:
            args += ['-s', self.state]
        # Add common optional arguments, if necessary.
        args += ['-r', int(self.temporary)]
        if self.hitValue is not None:
            args += ['-h', self.hitValue]
        if self.hitCondition:
            args += ['-o', self.hitCondition]
        
        args = [str(i) for i in args] # Return a stringified command version.
        return (args, data)


class spawnpoint(breakpoint):
    """A DBGP Spawnpoint.
    
    XXX Inheriting from koIDBGPBreakpoint is messy (because it is not a
        a proper superset). Should find a common base and use that.
    """
    # List of data attributes relevant for persistence and updating.
    # Note: This last must be kept in sync with the DBGP spawnpoint spec.
    _attrs = ["language", "type", "filename", "lineno", "state"]

    def init(self, lang, filename, line, state):
        self.language = lang
        self.type = 'spawn'
        self.filename = filename
        self.lineno = line
        self.state = state

    def getName(self):
        name = "%s, line %s" % (os.path.basename(self.filename), self.lineno)
        return name

    def __repr__(self):
        data = ("type:%(type)s filename:%(filename)s "
                "lineno:%(lineno)s state:%(state)s "
                % self.__dict__)
        return "<%s: %s>" % (self.__class__, data)

    def getSetArgs(self):
        """Return a list of options for a 'spawnpoint_set' command."""
        # tcl doesn't do any magic for us, we must be explicit
        filename = self.filename
        if filename[8:].startswith('file:/'):
            filename = self.filename[8:]
        args = ['-s', self.state,
                '-n', self.lineno,
                '-f', self.filename]
        args = [str(i) for i in args] # Return a stringified command version.
        return (args, None)


class contextType:
    def __init__(self):
        self.id = -1
        self.name = ''

    def initWithNode(self, node):
        # name="Local" id="0"
        if node.hasAttribute('id'):
            self.id = int(node.getAttribute('id'))
        self.name = node.getAttribute('name')
        
    def __repr__(self):
        return "%d: %s" %(self.id, self.name)
    

class stackFrame:
    def __init__(self):
        self.depth = -1
        self.filename = ''
        self.lineno = -1
        self.type = ''
        self.where = ''
        self.beginLine = 0
        self.beginOffset = 0
        self.endLine = 0
        self.endOffset = 0
        self.inputFrame = None

    def initWithNode(self, node):
        # level="%d" type="%s" filename="%s" lineno="%d" where="%s"
        if node.hasAttribute('level'):
            self.depth = int(node.getAttribute('level'))
        if node.hasAttribute('filename'):
            self.filename = node.getAttribute('filename')
        if node.hasAttribute('lineno'):
            self.lineno = int(node.getAttribute('lineno'))
        if node.hasAttribute('type'):
            self.type = node.getAttribute('type')
        if node.hasAttribute('where'):
            self.where = node.getAttribute('where')
        if node.hasAttribute('cmdbegin'):
            begin = node.getAttribute('cmdbegin')
            try:
                (self.beginLine, self.beginOffset) = begin.split(':')
            except:
                # if the attribute is invalid, ignore it
                log.warn('stack cmdbegin attribute is incorrect [%s]', begin)
        if node.hasAttribute('cmdend'):
            end = node.getAttribute('cmdend')
            try:
                (self.endLine, self.endOffset) = end.split(':')
            except:
                # if the attribute is invalid, ignore it
                log.warn('stack cmdend attribute is incorrect [%s]', end)
        input = node.getElementsByTagName('input')
        if len(input) > 0:
            # XXX more than one input frame?
            self.inputFrame = stackFrame()
            self.inputFrame.initWithNode(input[0])
        
    def __repr__(self):
        return "frame: %d %s(%d) %s %s" % \
            (self.depth, self.filename, self.lineno, self.type, self.where)


class property:
    _tooltip = None
    def __init__(self):
        _tooltip = None
        self.name = ''
        self.id = ''
        self.fullname = ''
        self.type = ''
        self.typeName = ''
        self.typeScheme = ''
        self.classname = ''
        self.facets = ''
        self.size = 0
        self.children = 0
        self.numchildren = 0
        self.address = 0
        self.recursive = 0
        self.encoding = ''
        self.key = ''
        self.value = ''
        self.node = None
        self.childProperties = []
        self.session = None
        self.contextId = 0
        self.depth = 0
    
    def _getCData(self, node):
        value = ''
        encoding = ''
        if node.hasAttribute('encoding'):
            encoding = node.getAttribute('encoding')
        for child in node.childNodes:
            if child.nodeType in [minidom.Node.TEXT_NODE,
                                  minidom.Node.CDATA_SECTION_NODE]:
                value = value + child.nodeValue
        try:
            if value and (self.encoding == 'base64' or encoding == 'base64'):
                value = base64.decodestring(value)
        except:
            pass
        return value

    def _decode_unicode_or_byte_string(self, s, name):
        # The only reason for this function is that PHP/Xdebug
        # leaves the name and fullname attributes as raw, utf-8 strings.
        # It should store them in name and fullname tags, with a
        # base64-encoding
        try:
            if type(s) == types.UnicodeType:
                return s.encode('latin1').decode('utf-8')
            elif type(s) == types.StringType:
                return s.decode('utf-8')
        except UnicodeDecodeError:
            proplog.warn("Unable to decode attr %s, value %r", name, s)
            return s        
         
    def initWithNode(self, session, node, context = 0, depth = 0):
        self.session = session
        # name="%s" fullname="%s" type="%s" children="%d" size="%d"
        # if children:
        #   page="%d" pagesize="%d" numchildren="%d"
        # if string type:
        #   encoding="%s"
        self.contextId = context
        self.depth = depth
        if node.hasAttribute('name'):
            self.name = self._decode_unicode_or_byte_string(node.getAttribute('name'),
                                                            'name')
        if node.hasAttribute('fullname'):
            self.fullname = self._decode_unicode_or_byte_string(node.getAttribute('fullname'),
                                                                'fullname')
        if node.hasAttribute('classname'):
            self.classname = node.getAttribute('classname')
        if node.hasAttribute('encoding'):
            self.encoding = node.getAttribute('encoding')
        proplog.debug("property encoding is %s", self.encoding)
        for child in node.childNodes:
            if child.nodeType == minidom.Node.ELEMENT_NODE and \
                   child.tagName == 'name':
                self.name = self._getCData(child)
            elif child.nodeType == minidom.Node.ELEMENT_NODE and \
                   child.tagName == 'fullname':
                self.fullname = self._getCData(child)
            elif child.nodeType == minidom.Node.ELEMENT_NODE and \
                   child.tagName == 'classname':
                self.classname = self._getCData(child)
            elif child.nodeType == minidom.Node.ELEMENT_NODE and \
                   child.tagName == 'value':
                self.value = self._getCData(child)
        
        self.type = node.getAttribute('type')
        if session and self.type in session._typeMap:
            self.typeName = session._typeMap[self.type].commonType
            self.typeScheme = session._typeMap[self.type].schemaType
        else:
            self.typeName = self.type
        
        if node.hasAttribute('size'):
            self.size = int(node.getAttribute('size'))
        if node.hasAttribute('children'):
            self.children = int(node.getAttribute('children'))
        if self.children:
            self.numchildren = 0
            page = 0
            pagesize = 0
            if node.hasAttribute('page'):
                page = int(node.getAttribute('page'))
            if node.hasAttribute('pagesize'):
                pagesize = int(node.getAttribute('pagesize'))
            if node.hasAttribute('numchildren'):
                self.numchildren = int(node.getAttribute('numchildren'))
            index = page * pagesize
            for child in node.childNodes:
                if child.nodeType == minidom.Node.ELEMENT_NODE and \
                   child.tagName == 'property':
                    p = property()
                    p.initWithNode(self.session, child, self.contextId, self.depth)
                    self.childProperties.insert(index, p)
                    index = index + 1
        if node.hasAttribute('key'):
            self.key = node.getAttribute('key')
        if node.hasAttribute('address'):
            self.address = node.getAttribute('address')
        # we may have more than one text node, get them all
        if not self.value:
            self.value = self._getCData(node)
        self.node = node
    
    def __repr__(self):
        return "name: %s type: %s value: %s" % \
                    (self.name, self.type, self.value)
    
    #void getChildren(in long page,
    #                [array, size_is(count)] out koIDBGPProperty properties,
    #                out PRUint32 count);
    def getChildren(self, page):
        pagesize = self.session.maxChildren
        start = page * pagesize
        end = start + pagesize
        if end >= self.numchildren:
            end = self.numchildren
        proplog.debug("getChildren num %d start %r end %r have %r",
                      self.numchildren, start, end, len(self.childProperties)) 
        if end > len(self.childProperties):
            proplog.debug("getChildren getting children")
            p = self.session.propertyGetEx(self.contextId,
                                                  self.depth,
                                                  self.fullname,
                                                  0,
                                                  '',
                                                  page)
            # property is a duplicate of self.  we need to copy it's
            # children into ours
            s = p.childProperties
            s.reverse()
            index = start
            while s:
                self.childProperties.insert(index, s.pop())
                index = index + 1
        proplog.debug("getChildren returning %d children", len(self.childProperties[start:end]))
        return self.childProperties[start:end]

    def getChildrenNextPage(self):
        if len(self.childProperties) >= self.numchildren:
            return None
        import math
        page = long(math.floor(len(self.childProperties) / self.session.maxChildren))
        return self.getChildren(page)
    
    def getAvailableChildren(self):
        return self.childProperties

    #void getAllChildren([array, size_is(count)] out koIDBGPProperty properties,
    #                out PRUint32 count);
    def getAllChildren(self):
        page = 0
        # self.childProperties = []
        while len(self.childProperties) < self.numchildren:
            #proplog.debug("getAllChildren getPage %d", page)
            if not self.getChildren(page):
                break
            page = page + 1
        return self.childProperties

    def setValue(self, value, type):
        prop = self.session.propertyUpdate(self, value, type)
        if prop:
            self.type = prop.type
            self.typeName = prop.typeName
            self.typeScheme = prop.typeScheme
            self.classname = prop.classname
            self.facets = prop.facets
            self.size = prop.size
            self.children = prop.children
            self.numchildren = prop.numchildren
            self.address = prop.address
            self.recursive = prop.recursive
            self.encoding = prop.encoding
            self.key = prop.key
            self.value = prop.value
            self.node = prop.node
            self.childProperties = prop.childProperties
            self.contextId = prop.contextId
            self.depth = prop.depth

    def getValue(self):
        if self.size > len(self.value):
            self.value = self.session.propertyValueEx(self.contextId, self.depth, self.fullname)
        return self.value

    _MAX_VALUE_LEN = 160
    def getTooltip(self, maxTooltipLength):
        if self._tooltip is None:
            value = self.value
            if self.numchildren > 0:
                # It's a container object - show a map of child items.
                values = [""]
                tooltip_length = 0
                if len(self.childProperties) == 0:
                    childProps = self.getChildrenNextPage()
                else:
                    childProps = self.childProperties
                while childProps:
                    for child in childProps:
                        childValue = self.session.propertyValue(child.fullname)
                        if len(childValue) > self._MAX_VALUE_LEN:
                            childValue = childValue[:self._MAX_VALUE_LEN] + "..."
                        child_tooltip = "%s: %s" % (child.name, childValue)
                        values.append(child_tooltip)
                        tooltip_length += len(child_tooltip)
                        if tooltip_length >= maxTooltipLength:
                            break
                    if tooltip_length >= maxTooltipLength:
                        break
                    # Load another page of children.
                    childProps = self.getChildrenNextPage()
                value = "\n\t".join(values)
            if len(value) > maxTooltipLength:
                value = value[:maxTooltipLength] + "\n\t..."
            if self.type:
                self._tooltip = "%s (%s): %s" % (self.name, self.type, value)
            else:
                self._tooltip = "%s: %s" % (self.name, value)
        return self._tooltip


class session(dbgp.serverBase.session):
    def __init__(self, sessionHost):
        dbgp.serverBase.session.__init__(self, sessionHost)

        # setup some event vars
        self._resp_cv = threading.Condition()
        self._responses = {}
        self.statusName = 'stopped'
        self.reason = 'ok'
        self.applicationId = None
        self.threadId = None
        self.parentId = None
        self.hostname = ""
        self._application = None

        self._features = {}
        self._supportedCommands = {}
        self._typeMap = {}
        
        self.supportsAsync = 0
        self.supportsHiddenVars = 0
        self.supportsPostmortem = 0
        self._resume = 0
        
        self.languageName = ''
        self.languageVersion = ''
        self.maxChildren = 0
        
        self.interactivePrompt = ''
        self.interactiveState = 0

    def _dispatch(self, size,response):
        # THREAD WARNING
        # this function is called from the command loop thread.  Do
        # not do anything here that will result in another command
        # being sent to the client, that will result in a lockup
        if size != len(response):
            raise DBGPError("Data length is not correct %d != %d" % (size,len(response)))
        #log.debug(response)
        dom = minidom.parseString(response)
        root = dom.documentElement
        packetType = root.localName
        if packetType == 'stream':
            type = root.getAttribute('type').lower()
            text = ''
            nodelist = root.childNodes
            for node in nodelist:
                if node.nodeType == node.TEXT_NODE:
                    text = text + node.data
                elif node.nodeType == node.CDATA_SECTION_NODE:
                    # Xdebug sends stdout in a cdata node - bug 77914.
                    text = text + node.data
            text = base64.decodestring(text)
            self._application.outputHandler(type, text)
        elif packetType == 'response':
            command = root.getAttribute('command')
            self._responseHandler(root)
            if command in ['stop','detach']:
                if command == 'stop':
                    self._application.shutdown()
                else:
                    self._application.releaseSession(self)
                try:
                    if self._socket:   # socket may already be closed.
                        self._socket.close()
                finally:
                    self._socket = None
                    self._stop = 1
                    
            if command in ['run', 'step_into', 'step_over',
                           'step_out', 'stop', 'detach', 'interact']:
                
                # any response command can initiate an interactive prompt
                # if it includes the prompt and more attributes
                if root.hasAttribute('more') and root.hasAttribute('prompt'):
                    self.interactiveState = int(root.getAttribute('more'))
                    self.interactivePrompt = root.getAttribute('prompt')
                else:
                    self.interactivePrompt = ''
                    self.interactiveState = 0
                    
                self._resume = 0
                # XXX notify state change now
                self.stateChange(root)
                return
            
        elif packetType == 'notify':
            name = root.getAttribute('name').lower()
            text = ''
            encoding = None
            nodelist = root.childNodes
            for node in nodelist:
                if node.nodeType == node.TEXT_NODE:
                    text = text + node.data
            if root.hasAttribute('encoding'):
                encoding = node.getAttribute('encoding')
            try:
                if text and encoding == 'base64':
                    text = base64.decodestring(text)
            except:
                pass
            #print "doing notify %s %s" %(name, text)
            self.notify(name, text, root)
        elif packetType == 'init':
            # we need to do some initialization commands, but we
            # cannot do that from this thread, which is currently
            # the cmdloop thread, because it would cause a deadlock.
            # this is a short lived thread, so should be fine
            log.debug('starting init thread')
            threading.Thread(target = self.initFeatures, args=(root,)).start()
    
    def initFeatures(self, initNode):
        # get our init information
        self.applicationId = initNode.getAttribute('appid')
        self.threadId = initNode.getAttribute('thread')
        self.parentId = initNode.getAttribute('parent')
        self.cookie = initNode.getAttribute('session')
        self.idekey = initNode.getAttribute('idekey')
        # If the client has set a specific hostname setting, then use it,
        # else we default to the socket connection address.
        if initNode.hasAttribute("hostname"):
            self.hostname = initNode.getAttribute('hostname')
        else:
            self.hostname = self._clientAddr[0]
        
        # we're now in a starting status.  force feed this
        # so that commands are not queued during startup
        self.statusName = 'starting'
        if initNode.hasAttribute('interactive'):
            self.statusName = 'interactive'
            self.interactivePrompt = initNode.getAttribute('interactive')
            #log.debug("setting initial interactove prompt to %s", self.interactivePrompt)

        # let the world know we're here
        if not self._sessionHost.initHandler(self, initNode):
            # we've closed the session
            return

        if initNode.hasAttribute('type') and initNode.getAttribute('type') == 'code_profiling':
            # Code profiling data - just ask the client for the profile data.
            log.debug("type is 'code_profiling' - so fetching the data")
            profile_data = self.getProfileData()
            log.debug('len(profile_data): %r', len(profile_data))
            self._application.codeProfileHandler(self, profile_data)
            self.stop()
            return

        # gather some necessary information for this session
        # any information we need during an async operation needs
        # to be retreived prior to async commands being done
        # we can ignore the error that is raised when something
        # is not supported
        log.debug('init thread running')
        try:
            self.supportsAsync = int(self.featureGet('supports_async'))
        except Exception, e:
            log.debug('init thread supportsAsync unknown')
            if self._stop: return
        try:
            self.languageName = self.featureGet('language_name')
        except Exception, e:
            log.debug('init thread languageName unknown')
            if self._stop: return
        try:
            self.languageVersion = self.featureGet('language_version')
        except Exception, e:
            log.debug('init thread languageVersion unknown')
            if self._stop: return
        try:
            self.maxChildren = int(self.featureGet('max_children'))
        except Exception, e:
            self.maxChildren = 0
            log.debug('init thread maxChildren unknown')
            if self._stop: return
        try:
            self.maxData = int(self.featureGet('max_data'))
        except Exception, e:
            self.maxData = 0
            log.debug('init thread maxData unknown')
            if self._stop: return
        try:
            self.maxDepth = int(self.featureGet('max_depth'))
        except Exception, e:
            self.maxDepth = 0
            log.debug('init thread maxDepth unknown')
            if self._stop: return
        try:
            self.featureGet('show_hidden')
            self.supportsHiddenVars = 1
        except Exception, e:
            self.supportsHiddenVars = 0
            log.debug('init supportsHiddenVars false')
            if self._stop: return
        try:
            self.featureGet('supports_postmortem')
            self.supportsPostmortem = 1
        except Exception, e:
            self.supportsPostmortem = 0
            log.debug('init supportsPostmortem false')
            if self._stop: return
        try:
            self.featureSet('multiple_sessions', '1')
        except Exception, e:
            log.debug('init thread multiple_sessions unknown')
            if self._stop: return
        try:
            # let the engine know it can send us notifications
            self.featureSet('notify_ok', '1')
        except Exception, e:
            log.debug('engine does not support notifications')
            if self._stop: return
        try:
            self._supportsOptionalCommand('break')
        except Exception, e:
            log.debug('init thread break unknown')
            if self._stop: return
        try:
            self._supportsOptionalCommand('eval')
        except Exception, e:
            log.debug('init thread eval unknown')
            if self._stop: return
        try:
            self._supportsOptionalCommand('stdin')
        except Exception, e:
            log.debug('init thread stdin unknown')
            if self._stop: return
        try:
            self._supportsOptionalCommand('detach')
        except Exception, e:
            log.debug('init thread detach unknown')
            if self._stop: return
        try:
            self._supportsOptionalCommand('interact')
        except Exception, e:
            log.debug('does not support interactive debugger')
            if self._stop: return
        try:
            self.breakpointLanguages = [l.lower() for l in self.featureGet('breakpoint_languages').split(',')]
        except Exception, e:
            if self._stop: return
            self.breakpointLanguages = [self.languageName]
        log.debug('init thread breakpoint_languages %r', self.breakpointLanguages)
        try:
            self._getTypeMap()
        except Exception, e:
            log.error('unable to retrieve typeMap from client')
            if self._stop: return
        # pass the url mapping to the engine
        try:
            if self._supportsOptionalCommand('urimap'):
                maps = self._sessionHost.getURIMappings()
                for map in maps:
                    self.featureSet('urimap', map)
        except Exception, e:
            log.debug('client does not support urimap feature')
            if self._stop: return
                
        # grab the breakpoint list now
        try:
            # some languages, eg. Tcl, have to do some processing before
            # breakpoints are set.  This notification allows hooks to be
            # added for that purpose
            if self._application and self._application.sessionCount() == 1:
                self._sessionHost.notifyStartup(self, initNode)
            
            err = self._sessionHost.breakpointManager.setSessionBreakpoints(self)
            #XXX Should, ideally, show this error to the user somehow. Ideas:
            #    - pop up a dialog and offer to cancel debugging?
            #    - status bar message?
            #    - display the breakpoint/spawnpoint markers slightly
            #      differently and remember this data so that the properties
            #      page for the breakpoint shows that this is not set on
            #      the session
            if err:
                log.error("the following breakpoints/spawnpoints could not "
                          "be set on this session:\n%s" % err)
        except Exception, e:
            log.error('breakpoints failed to be set properly')
            pass
        if not self._stop:
            # are we a new thread in the app?  If so, then just do
            # the run command now
            if self._application and self._application.sessionCount() > 1:
                self.resume(RESUME_GO)
                # no notifyInit for threads in an app
                return
            
            self._sessionHost.notifyInit(self, initNode)

    def notify(self, name, text, node):
        # "node" is the reponse node from the last continuation command
        #
        # THREAD WARNING
        # this function is called from the command loop thread.  Do
        # not do anything here that will result in another command
        # being sent to the client, that will result in a lockup
        # we were running, now we're at a break, or stopping

        log.info('session notify %s:%s name %s data %s',
                  self.applicationId,
                  self.threadId,
                  name, text)

    def stateChange(self, node):
        # "node" is the reponse node from the last continuation command
        #
        # THREAD WARNING
        # this function is called from the command loop thread.  Do
        # not do anything here that will result in another command
        # being sent to the client, that will result in a lockup
        # we were running, now we're at a break, or stopping
        if node:
            self.statusName = node.getAttribute('status')
            self.reason = node.getAttribute('reason')

        log.info('session %s:%s state %s',
                  self.applicationId,
                  self.threadId,
                  self.statusName)

    def addApplication(self, app):
        log.debug('setting session application')
        self._application = app
        
    def removeApplication(self):
        # [TM] Basically this is a poorly named session.finalize().
        log.debug('removing session application')
        # Tell the breakpoint manager that this debug session is shutting
        # down.
        self._sessionHost.breakpointManager.releaseSession(self)
        # don't remove the application var, just let the thread
        # know it should stop.
        self._stop = 1

    def _responseHandler(self, node):
        tid = None
        if node.hasAttribute('transaction_id'):
            tid = int(node.getAttribute('transaction_id'))
        if not tid:
            raise DBGPError('response without a transaction id')
        self._responses[tid] = node
        self._resp_cv.acquire()
        self._resp_cv.notify()
        self._resp_cv.release()

    def sendCommandWait(self, argv, data = None):
        if self._stop:
            raise DBGPError('command sent after session stopped')
        tid = self.sendCommand(argv, data)
        node = self._waitResponse(tid)
        err = node.getElementsByTagName('error')
        if err:
            errcode = err[0].getAttribute('code')
            msgnode = err[0].getElementsByTagName('message')
            msg = ''
            if msgnode:
                for child in msgnode[0].childNodes:
                    msg = msg + child.nodeValue
            if errcode:
                errcode = int(errcode)
            raise DBGPError(msg, errcode)
        return node

    def waitResponse(self, tid, timeout=5):
        return self._waitResponse(tid, timeout)

    def _waitResponse(self, tid, timeout=5):
        ticks = 0
        while not timeout or ticks < timeout:
            if tid in self._responses:
                resp = self._responses[tid]
                del self._responses[tid]
                return resp
            # XXX need the timeout here to prevent lockups
            # with tcl 11/25/03
            #if self._stop:
            ticks += 1
            self._resp_cv.acquire()
            self._resp_cv.wait(1)
            self._resp_cv.release()
        raise DBGPError('session timed out while waiting for response')

    def updateStatus(self):
        node = self.sendCommandWait(['status'])
        self.statusName = node.getAttribute('status')
        self.reason = node.getAttribute('reason')

    #/* status values */
    #readonly attribute long status;
    #readonly attribute long reason;
    def getLastError(self):
        pass
    
    def getBreakpointLanguages(self):
        return self.breakpointLanguages

    #/* feature commands */
    #wstring featureGet(in wstring name);
    def featureGet(self, name):
        self._supportsAsync()
        node = self.sendCommandWait(['feature_get', '-n', name])
        supported = node.getAttribute('supported')
        if not supported or not long(supported):
            raise DBGPError('Feature %s not supported' % name)
        value = ''
        for child in node.childNodes:
            if child.nodeType in [node.TEXT_NODE, node.CDATA_SECTION_NODE]:
                value += child.nodeValue
        isBase64 = node.hasAttribute('encoding') and \
                   node.getAttribute('encoding') == 'base64'
        if isBase64:
            try:
                value = base64.decodestring(value)
            except:
                pass
        return value or 0
        
    #boolean featureSet(in wstring name, in wstring value);
    def featureSet(self, name, value):
        self._supportsAsync()
        node = self.sendCommandWait(['feature_set', '-n', name, '-v', str(value)])
        if not node.hasAttribute('success') or not int(node.getAttribute('success')):
            raise DBGPError('Unable to set feature %s' % name)
        return 1
        
    def _supportsAsync(self):
        #if self.supportsAsync is None:
        #    try:
        #        node = self.sendCommandWait(['feature_get', '-n', 'supports_async'])
        #        self.supportsAsync = int(node.getAttribute('supported'))
        #    except DBGPError, e:
        #        self.supportsAsync = 0
        if not self.supportsAsync and self._resume > 0:
            raise DBGPError('Asynchronous commands are not supported')

    def _supportsOptionalCommand(self, commandName):
        if commandName not in self._supportedCommands:
            try:
                self.featureGet(commandName)
                self._supportedCommands[commandName] = 1
            except DBGPError, e:
                log.debug("command [%s] is not supported by debugger", commandName)
                self._supportedCommands[commandName] = 0
        return self._supportedCommands[commandName]
    
    def _noAsync(self, commandName):
        # Assert that this command is not being called asychronously (i.e.
        # this command is being called in a break state).
        if self._resume > 0:
            raise DBGPError('Cannot issue command [%s] asynchronously' % commandName)

    #/* continuation commands */
    #boolean resume(in long resumeAction);
    def resume(self, action):
        if self._resume > 0:
            raise DBGPError('Session already in resume state %d' % self._resume)

        # Notify breakpoint manager in case it has queue up
        # breakpoint/spawnpoint updates to send on to the session.
        self._sessionHost.breakpointManager.sendUpdatesToSession(self)

        self._resume = action
        self.statusName = 'running'
        self.sendCommand([resume_command_names[self._resume]])
        # set the status to running
        #self.stateChange(None)
        return 1

    #boolean break();
    def breakNow(self):
        self._supportsAsync()
        self.sendCommand(['break'])

    #boolean stop();
    def stop(self):
        # we cannot wait for a response here, as sometimes apps close
        # before we can read the response off the socket.
        tid = self.sendCommand(['stop'])
        return 1

    #boolean detach();
    def detach(self):
        if not self._supportsOptionalCommand('detach'):
            log.debug('client does not support detach!')
            return 0
        # we cannot wait for a response here, as sometimes apps close
        # before we can read the response off the socket.
        tid = self.sendCommand(['detach'])
        return 1

    #wstring interact(in wstring command);
    def interact(self, command):
        self._supportsAsync()
        if not self._supportsOptionalCommand('interact'):
            log.debug('client does not support interact!')
            return 0
        self.statusName = 'running'

        # turn off interactive mode.  It gets turned on again when we receive
        # the response to this command. It needs to be turned off because we
        # might recieved stdin requests before we receive an interact response.
        # We also must do this before sending the command to avoid the
        # response happening before we turn this off (threads, happy happy joy joy)
        self.interactivePrompt = ''

        if command is None:
            tid = self.sendCommand(['interact', '-m', '0'])
        else:
            tid = self.sendCommand(['interact', '-m', '1'], command)
        
        return tid

    #/* stack commands */
    #long stackDepth();
    def stackDepth(self):
        self._noAsync('stack_depth')
        node = self.sendCommandWait(['stack_depth'])
        return node.getAttribute('depth')

    #koIDBGPStackFrame stackGet(in long depth);
    def stackGet(self, depth):
        self._noAsync('stack_get')
        node = self.sendCommandWait(['stack_get', '-d', str(depth)])
        for child in node.childNodes:
            if child.nodeType != node.ELEMENT_NODE or child.tagName != 'stack': continue
            frame = stackFrame()
            frame.initWithNode(child)
            return frame
        return None

    #void stackFramesGet([array, size_is(count)] out koIDBGPStackFrame frames,
    #                  out PRUint32 count);
    def stackFramesGet(self):
        self._noAsync('stack_get')
        node = self.sendCommandWait(['stack_get'])
        frames = []
        children = node.getElementsByTagName('stack')
        for child in children:
            frame = stackFrame()
            frame.initWithNode(child)
            frames.append(frame)
        return frames

    #/* context commands */
    #void contextNames([retval, array, size_is(count)] out koIDBGPContextType contextTypes,
    #                  [optional] out PRUint32 count);
    def contextNames(self):
        self._noAsync('context_names')
        node = self.sendCommandWait(['context_names'])
        contextList = []
        children = node.getElementsByTagName('context')
        for child in children:
            context = contextType()
            context.initWithNode(child)
            contextList.append(context)
        return contextList

    #void contextGet(in long id,
    #                [array, size_is(count)] out koIDBGPProperty properties,
    #                out PRUint32 count);
    def contextGet(self, contextId, depth):
        self._noAsync('context_get')
        node = self.sendCommandWait(['context_get', '-c', str(contextId), '-d', str(depth)])
        propertyList = []
        for child in node.childNodes:
            if child.nodeType == minidom.Node.ELEMENT_NODE and \
               child.tagName == 'property':
                p = property()
                p.initWithNode(self, child, contextId, depth)
                propertyList.append(p)
        return propertyList
    
    #/* property commands */
    #koIDBGPProperty propertyGet(in long contextId,
    #                            in long stackDepth,
    #                            in wstring fullname,
    #                            in long maxData,
    #                            in long dataType,
    #                            in long dataPage);
    def propertyGet(self, fullname):
        return self.propertyGetEx(0, 0, fullname, 0, '', 0)

    def propertyGetEx(self, contextId, stackDepth, fullname, maxData, dataType, dataPage, address=""):
        # This can fire with a hover tip while the program is running, so
        # ignore it.
        if self._resume > 0:
            return
        cmd = ['property_get', '-c', str(contextId),
                '-d', str(stackDepth), '-n', fullname]
        if maxData:
            cmd += ['-m', str(maxData)]
        if dataType:
            cmd += ['-t', dataType]
        if dataPage:
            cmd += ['-p', str(dataPage)]
        if address and len(address) > 0:
            cmd += ['-a', str(address)]
        try:
            node = self.sendCommandWait(cmd)
            p = property()
            p.initWithNode(self, node.firstChild, contextId, stackDepth)
        except DBGPError, e:
            # create an empty var with the exception for the value
            p = property()
            p.session = self
            p.context = contextId
            p.depth = stackDepth
            p.fullname = fullname
            p.name = fullname
            p.value = getErrorInfo(e)[1]
            p.type = 'exception'
        return p
    
    #koIDBGPProperty propertySet(in long contextId,
    #                    in long stackDepth,
    #                    in wstring name,
    #                    in wstring value);
    def propertySet(self, name, value):
        return self.propertySetEx(0, 0, name, value)

    def propertySetEx(self, contextId, stackDepth, name, value):
        self._noAsync('property_set')
        args = ['property_set', '-c', str(contextId), '-d',
                str(stackDepth), '-n', name]
        node = self.sendCommandWait(args, value)
        if node.hasAttribute('success'):
            if int(node.getAttribute('success')):
                return self.propertyGetEx(contextId, stackDepth, name, 0, '', 0)
            else:
                raise DBGPError("Unable to set the property value.")
        return None

    def propertyUpdate(self, prop, value, type):
        self._noAsync('property_set')
        args = ['property_set', '-c', str(prop.contextId), '-d',
                str(prop.depth), '-n', prop.fullname]
        if prop.key:
            args += ['-k', prop.key]
        if prop.address:
            prop_address = prop.address
            args += ['-a', prop_address]
        else:
            prop_address = ""
        if type:
            args += ['-t', type]
        node = self.sendCommandWait(args, value)
        if node.hasAttribute('success'):
            if int(node.getAttribute('success')):
                return self.propertyGetEx(prop.contextId, prop.depth, prop.fullname, 0, '', 0, prop_address)
            else:
                raise DBGPError("Unable to update the variable.")
        return None
        
    #wstring propertyValue(in long contextId,
    #                    in long stackDepth,
    #                    in wstring name);
    def propertyValue(self, name):
        return self.propertyValueEx(0, 0, name)

    def propertyValueEx(self, contextId, stackDepth, name):
        self._noAsync('property_value')
        args = ['property_value', '-c', str(contextId), '-d',
                str(stackDepth), '-n', name]
        node = self.sendCommandWait(args)

        encoding = None
        if node.hasAttribute('encoding'):
            encoding = node.getAttribute('encoding')

        value = ''
        # we may have more than one text node, get them all
        for child in node.childNodes:
            if child.nodeType in [minidom.Node.TEXT_NODE,
                                  minidom.Node.CDATA_SECTION_NODE]:
                value = value + child.nodeValue
        try:
            if value and encoding == 'base64':
                value = base64.decodestring(value)
        except:
            pass

        return value


    #---- breakpoint commands
    def breakpointSet(self, bp):
        """Set the given breakpoint on this session.
        
        Returns the session's assigned ID (a string) for the new breakpoint.
        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointSet(bp='%s')", bp.getName())
        self._supportsAsync()
        bpargs, bpdata = bp.getSetArgs()
        args = ["breakpoint_set"] + bpargs
        node = self.sendCommandWait(args, bpdata)
        return node.getAttribute("id")

    def breakpointUpdate(self, bpid, bp, attrs=None):
        """Update the given breakpoint.
        
            "bpid" is the session's ID for this breakpoint.
            "bp" is a breakpoint instance from which to update
            "attrs" (optional) is a list of attributes that are meant to be
                updated. If None (or the empty list), then all attributes
                are updated.

        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointUpdate(bpid=%r, bp='%s', attrs=%r)",
                    bpid, bp.getName(), attrs)
        self._supportsAsync()
        args = ["breakpoint_update", "-d", str(bpid)]
        if not attrs:  # False means update all supported attributes.
            args += ["-s", bp.state]
            args += ["-n", str(bp.lineno)]
            args += ["-h", str(bp.hitValue)]
            if bp.hitCondition:
                args += ["-o", bp.hitCondition]
            args += ["-r", str(int(bp.temporary))]
        else: # Only update the specified attributes.
            for attr in attrs:
                if attr == "state":
                    args += ["-s", bp.state]
                elif attr == "lineno":
                    args += ["-n", str(bp.lineno)]
                elif attr == "hitValue":
                    args += ["-h", str(bp.hitValue)]
                elif attr == "hitCondition":
                    args += ["-o", bp.hitCondition]
                elif attr == "temporary":
                    args += ["-r", str(int(bp.temporary))]
        if bp.type in 'conditional':
            bpdata = bp.expression
        else:
            bpdata = None
        bplog.debug("session %r: '%r', data='%r'", (self.applicationId, self.threadId), args, bpdata)
        node = self.sendCommandWait(args, bpdata)

    def breakpointGet(self, bpid):
        """Get the breakpoint with the given session breakpoint id.
        
        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointGet(bpid=%r)", bpid)
        self._supportsAsync()
        node = self.sendCommandWait(["breakpoint_get", "-d", str(bpid)])
        children = node.getElementsByTagName("breakpoint")
        if not children:
            return None
        bp = breakpoint()
        bp.initWithNode(children[0])
        return bp

    def breakpointEnable(self, bpid):
        """Enable the breakpoint with the given session breakpoint id.

        NOTE: This command is OBSOLETE. Use breakpointUpdate() instead.
        
        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointEnable(bpid=%r)", bpid)
        self._supportsAsync()
        self.sendCommandWait(["breakpoint_enable", "-d", str(bpid)])

    def breakpointDisable(self, bpid):
        """Disable the breakpoint with the given session breakpoint id.

        NOTE: This command is OBSOLETE. Use breakpointUpdate() instead.
        
        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointDisable(bpid=%r)", bpid)
        self._supportsAsync()
        node = self.sendCommandWait(["breakpoint_disable", "-d", str(bpid)])

    def breakpointRemove(self, bpid):
        """Remove the breakpoint with the given session breakpoint id.

        Raises a DBGPError if the command fails.
        """
        bplog.debug("session.breakpointRemove(bpid=%r)", bpid)
        self._supportsAsync()
        node = self.sendCommandWait(["breakpoint_remove", "-d", str(bpid)])

    def breakpointList(self):
        """Return a list of all breakpoints for this session.

        Raises a DBGPError if the command fails.
        """
        self._supportsAsync()
        node = self.sendCommandWait(["breakpoint_list"])
        children = node.getElementsByTagName("breakpoint")
        breakpoints = []
        for child in children:
            bp = breakpoint()
            bp.initWithNode(child)
            breakpoints.append(bp)
        return breakpoints


    #---- spawnpoint commands
    def spawnpointSet(self, sp):
        """Set the given spawnpoint on this session.
        
        Returns the session's assigned ID (a string) for the new spawnpoint.
        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_set")
        spArgs, spData = sp.getSetArgs()
        args = ["spawnpoint_set"] + spArgs
        node = self.sendCommandWait(args, spData)
        return node.getAttribute("id")

    def spawnpointUpdate(self, spid, sp, attrs=None):
        """Update the given spawnpoint.
        
            "spid" is the session's ID for this spawnpoint.
            "sp" is a spawnpoint instance from which to update
            "attrs" (optional) is a list of attributes that are meant to be
                updated. If None, then all attributes are updated.

        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_update")
        args = ["spawnpoint_update", "-d", spid]
        if attrs is None:  # None means update all supported attributes.
            args += ["-s", str(sp.state)]
            args += ["-n", str(sp.lineno)]
        else: # Only update the specified attributes.
            for attr in attrs:
                if attr == "state":
                    args += ["-s", str(sp.state)]
                elif attr == "lineno":
                    args += ["-n", str(sp.lineno)]
        node = self.sendCommandWait(args)

    def spawnpointGet(self, spid):
        """Get the spawnpoint with the given session spawnpoint id.
        
        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_get")
        node = self.sendCommandWait(["spawnpoint_get", "-d", str(spid)])
        children = node.getElementsByTagName("spawnpoint")
        if not children:
            return None
        sp = spawnpoint()
        sp.initWithNode(children[0])
        return sp

    def spawnpointEnable(self, spid):
        """Enable the spawnpoint with the given session spawnpoint id.

        NOTE: This command is OBSOLETE. Use spawnpointUpdate() instead.
        
        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_enable")
        self.sendCommandWait(["spawnpoint_enable", "-d", str(spid)])

    def spawnpointDisable(self, spid):
        """Disable the spawnpoint with the given session spawnpoint id.

        NOTE: This command is OBSOLETE. Use spawnpointUpdate() instead.
        
        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_disable")
        node = self.sendCommandWait(["spawnpoint_disable", "-d", str(spid)])

    def spawnpointRemove(self, spid):
        """Remove the spawnpoint with the given session spawnpoint id.

        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_remove")
        node = self.sendCommandWait(["spawnpoint_remove", "-d", str(spid)])

    def spawnpointList(self):
        """Return a list of all spawnpoints for this session.

        Raises a DBGPError if the command fails.
        """
        self._noAsync("spawnpoint_list")
        node = self.sendCommandWait(["spawnpoint_list"])
        children = node.getElementsByTagName("spawnpoint")
        spawnpoints = []
        for child in children:
            sp = spawnpoint()
            sp.initWithNode(child)
            spawnpoints.append(sp)
        return spawnpoints


    #/* eval */
    #koIDBGPProperty evalString(in wstring expression);
    def evalString(self, expression):
        self._noAsync('eval')
        l = len(expression)
        try:
            node = self.sendCommandWait(['eval', '-l', str(l)], expression)
            pnodes = node.getElementsByTagName('property')
            if pnodes:
                p = property()
                p.initWithNode(self, pnodes[0])
                p.name = expression
                return p
        except DBGPError, e:
            # create an empty var with the exception for the value
            p = property()
            p.session = self
            p.context = 0
            p.depth = 0
            p.fullname = expression
            p.name = expression
            p.value = getErrorInfo(e)[1]
            p.type = 'exception'
            return p
        return None
    
    def _getTypeMap(self):
        self._noAsync('typemap_get')
        node = self.sendCommandWait(['typemap_get'])
        self._typeMap = {}
        children = node.getElementsByTagName('map')
        for child in children:
            typ = dataType()
            typ.initWithNode(child)
            self._typeMap[typ.languageType] = typ

    #void getTypeMap([array, size_is(count)] out koIDBGPDataType dateTypes,
    #                  out PRUint32 count);
    def getTypeMap(self):
        if not self._typeMap:
            self._getTypeMap()
        return self._typeMap.values()
    
    def getDataType(self, commonType):
        for typ in self.getTypeMap():
            if typ.commonType == commonType:
                return typ
        return None

    ## Gets the sourcecode for the named file.
    #wstring getSourceCode(in wstring filename);
    def getSourceCode(self, filename, startline, endline):
        self._noAsync('source')
        cmd = ['source']
        if filename:
            cmd += ['-f', filename]
        if startline:
            cmd += ['-b', str(startline)]
        if endline:
            cmd += ['-e', str(endline)]
        node = self.sendCommandWait(cmd)
        text = ''
        for c in node.childNodes:
            text = text + c.nodeValue
        try:
            text = base64.decodestring(text)
        except:
            pass
        return text

    def getProfileData(self):
        self._noAsync('profile_data')
        cmd = ['profile_data']
        node = self.sendCommandWait(cmd)
        text = ''
        for c in node.childNodes:
            text = text + c.nodeValue
        try:
            text = base64.decodestring(text)
        except:
            pass
        if node.hasAttribute('datatype') and \
           node.getAttribute('datatype') == 'zip':
            # The profile information is wrapped inside a zip archive.
            try:
                from zipfile import ZipFile
                from cStringIO import StringIO
                zipfile = StringIO(text)
                z = ZipFile(zipfile)
                assert len(z.filelist) == 1
                filename = z.filelist[0]
                text = z.read(filename)
            except:
                # TODO: Properly handle and notify any errors.
                pass
        return text

    #sendStdin(in wstring data, in long size);
    def sendStdin(self, data, size):
        if not self._supportsOptionalCommand('stdin'):
            log.debug('client does not support stdin!')
            return 0
        log.debug('sending stdin [%s]!', data)
        node = self.sendCommandWait(['stdin'], data)
        return node.getAttribute('success')

    #setStdinHandler(in koIFile file);
    def setStdinHandler(self, file):
        if not self._supportsOptionalCommand('stdin'):
            log.debug('client does not support stdin!')
            return 0
        if file:
            cmd = ['stdin', '-c', '1']
        else:
            cmd = ['stdin', '-c', '0']
        node = self.sendCommandWait(cmd)
        return node.getAttribute('success')

    #setStdoutHandler(in koIFile file, in long mode);
    def setStdoutHandler(self, file, mode):
        node = self.sendCommandWait(['stdout', '-c', str(mode)])
        return node.getAttribute('success')

    #setStderrHandler(in koIFile file, in long mode);
    def setStderrHandler(self, file, mode):
        node = self.sendCommandWait(['stderr', '-c', str(mode)])
        return node.getAttribute('success')

def _sessionSort(a, b):
    return cmp(a.threadId, b.threadId)

class application:
    def __init__(self, appMgr):
        self.appMgr = appMgr
        self._watchedvars = {}
        self._sessions = {}
        self.currentSession = None
        self._stdin = self._stdout = self._stderr = None

    def addSession(self, session):
        log.debug('pid %r adding thread %r', session.applicationId, session.threadId)
        self._sessions[session.threadId] = session
        session.addApplication(self)
        if not self.currentSession:
            self.currentSession = session
    
    def haveSession(self, session):
        return session in self._sessions.values()

    def releaseSession(self, session):
        log.debug('removing session')
        session.removeApplication()
        del self._sessions[session.threadId]
        # reset current thread now or quit
        if len(self._sessions) < 1:
            self.shutdown()
            return
        if session == self.currentSession:
            self.currentSession = self._sessions.values()[0]
        
    def getSessionList(self):
        l = self._sessions.values()
        l.sort(_sessionSort)
        return l

    def shutdown(self):
        if self._stdin:
            self._stdin.close()
        for ses in self._sessions.keys():
            self._sessions[ses].removeApplication()
            if self._sessions.has_key(ses):
                del self._sessions[ses]
        self.appMgr.releaseApplication(self)

    def sessionCount(self):
        return len(self._sessions.keys())

    #sendStdin(in wstring data, in long size);
    def sendStdin(self, data, size):
        return self.currentSession.sendStdin(data, size);
        
    #setStdinHandler(in koIFile file);
    def setStdinHandler(self, file):
        # XXX need to set for all sessions?
        ok = self.currentSession.setStdinHandler(file)
        if ok:
            self._stdin = file
            threading.Thread(target = self._stdinHandlerThread).start()
        return ok

    def _stdinHandlerThread(self):
        log.debug('starting stdin thread')
        while 1:
            try:
                #log.debug('reading console data...')
                data = self._stdin.read(1024)
                if not data:
                    self.currentSession.setStdinHandler(None)
                    log.debug('empty data from console, stdin closed')
                    break
                
                log.debug('writing stdin data...[%s]', data)
                self.sendStdin(data, len(data))
            except Exception, e:
                log.exception(e)
                break
        log.debug('quiting stdin thread')
                
    #setStdoutHandler(in koIFile file, in long mode);
    def setStdoutHandler(self, file, mode):
        # XXX need to set for all sessions?
        ok = self.currentSession.setStdoutHandler(file, mode)
        if ok:
            self._stdout = file
        return ok
    
    #setStderrHandler(in koIFile file, in long mode);
    def setStderrHandler(self, file, mode):
        # XXX need to set for all sessions?
        ok = self.currentSession.setStderrHandler(file, mode)
        if ok:
            self._stderr = file
        return ok

    def outputHandler(self, stream, text):
        log.debug('outputHandler [%r] [%r]', stream, text)
        if stream == 'stdout' and self._stdout:
            self._stdout.write(text)
        elif stream == 'stderr' and self._stderr:
            self._stderr.write(text)


class appManager:
    appList = {}
    _lock = threading.Lock() 

    def __init__(self, debugMgr):
        self.debugMgr = debugMgr
        
    def getApplication(self, session):
        self._lock.acquire()
        try:
            if session.applicationId not in self.appList:
                log.debug('creating application class for pid %r',session.applicationId)
                self.appList[session.applicationId] = application(self)
            else:
                log.debug('getting application class for pid %r',session.applicationId)
            if not self.appList[session.applicationId].haveSession(session):
                self.appList[session.applicationId].addSession(session)
        finally:
            self._lock.release()
        return self.appList[session.applicationId]
    
    def releaseApplication(self, appinst):
        # kill command was issued, remove all references
        appid = appinst.currentSession.applicationId
        self._lock.acquire()
        try:
            if appid not in self.appList:
                # XXX raise exception?
                return
            data = self.appList[appid]
            del self.appList[appid]
        finally:
            self._lock.release()

    def shutdown(self):
        for app in self.appList.values():
            app.shutdown()


class listener(dbgp.serverBase.listener):
    def startNewSession(self, client, addr):
        # start a new thread that is the host connection
        # for this debugger session
        sessionHost = session(self._session_host)
        sessionHost.start(client, addr)


class breakpointManager:
    _lock = threading.Lock()
    _breakpoints = {} # mapping of breakpoint guid to breakpoint instance

    def __init__(self):
        self._guidCounter = 0 # used to assign a unique self._id to each bp

        # Keep track of what debug sessions have what breakpoints and what
        # ids they have assigned for them. Essentially this information is
        # a cache because _technically_ we could query every debug session
        # for this info every time.
        # - Note: A session id is defined here as the 2-tuple
        #      (session.applicationId, session.threadId)
        #   because I [TrentM] am not sure if threadId's are necessarily
        #   unique across application's.
        self._allSessionBPIDs = {
            # <session id>: {<breakpoint guid>: <session bpid>, ...}
        }
        self._queuedSessionCommands = {
            # <session id>: <FIFO of commands to send on break state>
            #   where each "command" is a 2-tuple:
            #       (<set|remove|update>, <tuple of args>)
            #   e.g.:
            #       ("set",    (<breakpoint instance>,))
            #       ("remove", (<breakpoint instance>,))
            #       ("update", (<breakpoint instance>, <attrs to update>))
        }
        self._sessions = {
            # <session id>: <session instance>
        }

    def _makeBreakpointGuid(self):
        guid = self._guidCounter
        self._guidCounter += 1
        return guid

    # The .addBreakpoint*() methods (and .addSpawnpoint()) are convenience
    # methods for the more general .addBreakpoint() to add breakpoints of
    # specific types.
    def addBreakpointConditional(self, lang, cond, file, line, state,
                                 temporary, hitValue, hitCondition):
        bp = breakpoint()
        bp.initConditional(lang, cond, file, line, state, temporary,
                           hitValue, hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addBreakpointLine(self, lang, file, line, state, temporary,
                          hitValue, hitCondition):
        bp = breakpoint()
        bp.initLine(lang, file, line, state, temporary, hitValue,
                    hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addBreakpointException(self, lang, exceptionName, state, temporary,
                               hitValue, hitCondition):
        bp = breakpoint()
        bp.initException(lang, exceptionName, state, temporary, hitValue,
                         hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addBreakpointCall(self, lang, func, filename, state, temporary,
                          hitValue, hitCondition):
        bp = breakpoint()
        bp.initCall(lang, func, filename, state, temporary, hitValue,
                    hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addBreakpointReturn(self, lang, func, filename, state, temporary,
                            hitValue, hitCondition):
        bp = breakpoint()
        bp.initReturn(lang, func, filename, state, temporary, hitValue,
                      hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addBreakpointWatch(self, lang, watch, file, line, state,
                            temporary, hitValue, hitCondition):
        bp = breakpoint()
        bp.initWatch(lang, watch, file, line, state, temporary,
                           hitValue, hitCondition)
        self.addBreakpoint(bp)
        return bp
    def addSpawnpoint(self, lang, filename, line, state):
        sp = spawnpoint()
        sp.init(lang, filename, line, state)
        # we just stuff our spawnpoints into the breakpoints
        self.addBreakpoint(sp)
        return sp

    def addBreakpoint(self, bp):
        self._lock.acquire()
        try:
            bp._guid = self._makeBreakpointGuid()
            self._breakpoints[bp.getGuid()] = bp
            
            # Pass this new breakpoint onto any current debug session for
            # which this is appropriate.
            for session in self._sessions.values():
                try:
                    self._setSessionBreakpointOrQueueIt(session, bp)
                except (DBGPError, COMException), ex:
                    log.exception(ex)
                    pass # XXX should report to user somehow

            self.postAddBreakpoint(bp)
        finally:
            self._lock.release()

    def postAddBreakpoint(self, bp):
        """Method stub to allow subclasses to react to a breakpoint
        addition while the breakpoints lock is held.
        """
        pass

    def removeBreakpoint(self, guid):
        self._lock.acquire()
        try:
            if self._breakpoints.has_key(guid):
                bp = self._breakpoints[guid]
                del self._breakpoints[guid]

                # Remove this breakpoint from any session that currently has it.
                for sessId, sessionBPIDs in self._allSessionBPIDs.items():
                    if guid in sessionBPIDs:
                        session = self._sessions[sessId]
                        self._removeSessionBreakpointOrQueueIt(session, bp)

                self.postRemoveBreakpoint(bp)
        finally:
            self._lock.release()
    
    def postRemoveBreakpoint(self, bp):
        """Method stub to allow subclasses to react to a breakpoint
        removal while the breakpoints lock is held.
        """
        pass

    def removeAllBreakpoints(self):
        self._lock.acquire()
        try:
            # Remove all breakpoints from all current debug sessions.
            #XXX:PERF _Could_ optimize this if necessary.
            for sessId, sessionBPIDs in self._allSessionBPIDs.items():
                for guid in sessionBPIDs.keys():
                    try:
                        session = self._sessions[sessId]
                    except (KeyError, ItemError), ex:
                        log.exception("Failed to find session %r", sessId)
                        continue
                    try:
                        bp = self._breakpoints[guid]
                    except (KeyError, ItemError), ex:
                        log.exception("Failed to find breakpoint %r in session %r", guid, sessId)
                        continue
                    self._removeSessionBreakpointOrQueueIt(session, bp)

            self._breakpoints = {}

            self.postRemoveAllBreakpoints()
        finally:
            self._lock.release()
    
    def postRemoveAllBreakpoints(self):
        """Method stub to allow subclasses to react to a breakpoint list
        reset while the breakpoints lock is held.
        """
        pass

    def updateBreakpoint(self, guid, newBp):
        self._lock.acquire()
        try:
            bp = self._breakpoints[guid]
            self.preUpdateBreakpoint(bp)
            attrs = bp.update(newBp)

            # Update the breakpoint in all current debug sessions that
            # have this breakpoint.
            # Note: We are presuming here that the breakpoint update did not
            #       all of the sudden make this breakpoint applicable to a
            #       debug session when it previously was not.
            for sessId, sessionBPIDs in self._allSessionBPIDs.items():
                if guid in sessionBPIDs:
                    session = self._sessions[sessId]
                    self._updateSessionBreakpointOrQueueIt(session, bp, attrs)

            self.postUpdateBreakpoint(bp, attrs)
        finally:
            self._lock.release()

    def preUpdateBreakpoint(self, bp):
        """Method stub to allow subclasses to react _before_ a breakpoint
        change while the breakpoints lock is held.
        
            "bp" is the changed breakpoint.
        """
        pass

    def postUpdateBreakpoint(self, bp, attrs):
        """Method stub to allow subclasses to react to a breakpoint change
        while the breakpoints lock is held.
        
            "bp" is the changed breakpoint.
            "attrs" is a list of breakpoint attributes that changed.
        """
        pass

    def getBreakpointsForLanguage(self, lang):
        self._lock.acquire()
        try:
            #XXX Currently don't have to allow the "not bp.language": all
            #    breakpoints have their language attribute set.
            return [bp for bp in self._breakpoints.values()
                    if not bp.language or bp.language.lower() == lang.lower()]
        finally:
            self._lock.release()


    #---- Managing session breakpoints.
    # The first three methods are public and are meant to be called by the
    # application (or some other session manager) and the session's.
    # The rest are internal methods used to keep breakpoint info in sync
    # between here and each session.

    def setSessionBreakpoints(self, session):
        """Add the relevant breakpoints to this session.
        
        Returns a newline-separated list of breakpoints (and reasons) that
        did not get properly set on the session.
        """
        #XXX Breakpoints should only be added once for each
        #    "application" in DBGP-parlance. In DBGP-land there is one
        #    "Session" per thread, yet all threads share the same breakpoints.
        #    At least, that is my understanding of the intention from Shane.
        bplog.debug("breakpointManager.setSessionBreakpoints(session)")
        breakpoints = [bp for bp in self._breakpoints.values()]
        sessId = (session.applicationId, session.threadId)
        self._sessions[sessId] = session
        self._allSessionBPIDs[sessId] = {}
        self._queuedSessionCommands[sessId] = []
        failed = [] # list of bp's that did not get set on the session
        for bp in breakpoints:
            try:
                self.__setSessionBreakpoint(session, bp)
            except (DBGPError, COMException), ex:
                errno, errmsg = getErrorInfo(ex)
                failed.append("%s (%s)" % (bp.getName(), errmsg))
        return '\n'.join(failed)

    def releaseSession(self, session):
        """Release references to this session, it is shutting down."""
        sessId = (session.applicationId, session.threadId)
        if self._allSessionBPIDs.has_key(sessId):
            del self._allSessionBPIDs[sessId]
        if self._queuedSessionCommands.has_key(sessId):
            del self._queuedSessionCommands[sessId]
        if self._sessions.has_key(sessId):
            del self._sessions[sessId]

    def sendUpdatesToSession(self, session):
        """Any queued breakpoint/spawnpoint updates should be forwarded onto
        session.
        """
        self._sendQueuedSessionCommands(session)

    def _setSessionBreakpointOrQueueIt(self, session, bp):
        """Set the given breakpoint on the given session and update local
        cache information on this.
        
        If the session is not in a break state, this command is queued up
        until it is.
        """
        if session.statusName not in ["break", "starting"]:
            # DBGP client sessions can only accept breakpoint changes when
            # in the break state. We will queue up this command for later.
            # Note that the Python and Ruby back-ends *can* process
            # async requests, but we don't have a way of processing
            # the responses asynchronously, and tying the UI's guid
            # with the back-end's breakpoint ID.
            command = ("set", (bp,))
            sessId = (session.applicationId, session.threadId)
            self._queuedSessionCommands[sessId].append(command)
        else:
            self._sendQueuedSessionCommands(session)
            self.__setSessionBreakpoint(session, bp)

    def __setSessionBreakpoint(self, session, bp):
        # We are REALLY setting the breakpoint on the session now.
        sessId = (session.applicationId, session.threadId)
        if bp.type == "spawn":
            bpid = session.spawnpointSet(bp)
        else:
            bpid = session.breakpointSet(bp)
        self._allSessionBPIDs[sessId][bp.getGuid()] = bpid
        bplog.info("set '%s' %spoint on session %s: bpid='%s'",
                   bp.getName(), (bp.type=="spawn" and "spawn" or "break"),
                   sessId, bpid)

    def _removeSessionBreakpointOrQueueIt(self, session, bp):
        """Remove the given breakpoint from the given session and update
        local cache info.
        
        If the session is not in a break state, this command is queued up
        until it is.
        """
        if session.statusName != "break":
            # DBGP client sessions can only accept breakpoint changes when
            # in the break state. We will queue up this command for later.
            command = ("remove", (bp,))
            sessId = (session.applicationId, session.threadId)
            self._queuedSessionCommands[sessId].append(command)
        else:
            self._sendQueuedSessionCommands(session)
            self.__removeSessionBreakpoint(session, bp)

    def __removeSessionBreakpoint(self, session, bp):
        # We are REALLY removing the breakpoint from the session now.
        sessId = (session.applicationId, session.threadId)
        sessionBPIDs = self._allSessionBPIDs[sessId]
        guid = bp.getGuid()
        bpid = sessionBPIDs[guid] # the session's ID for this bp
        if bp.type == "spawn":
            session.spawnpointRemove(bpid)
        else:
            session.breakpointRemove(bpid)
        del sessionBPIDs[guid]
        bplog.info("removed '%s' %spoint from session %s",
                   bp.getName(), (bp.type=="spawn" and "spawn" or "break"),
                   sessId)

    def _updateSessionBreakpointOrQueueIt(self, session, bp, attrs):
        """Update the given attributes of the given breakpoint on the
        given debug session.
        
        If the session is not in a break state, this command is queued up
        until it is.
        """
        if session.statusName != "break":
            # DBGP client sessions can only accept breakpoint changes when
            # in the break state. We will queue up this command for later.
            command = ("update", (bp, attrs))
            sessId = (session.applicationId, session.threadId)
            self._queuedSessionCommands[sessId].append(command)
        else:
            self._sendQueuedSessionCommands(session)
            self.__updateSessionBreakpoint(session, bp, attrs)

    def __updateSessionBreakpoint(self, session, bp, attrs):
        # We are REALLY updating the breakpoint on the session now.
        sessId = (session.applicationId, session.threadId)
        sessionBPIDs = self._allSessionBPIDs[sessId]
        guid = bp.getGuid()
        bpid = sessionBPIDs[guid] # the session's ID for this bp
        if bp.type == "spawn":
            session.spawnpointUpdate(bpid, bp, attrs)
        else:
            session.breakpointUpdate(bpid, bp, attrs)
        bplog.info("updated '%s' %spoint on session %s: attrs=%s",
                   bp.getName(), (bp.type=="spawn" and "spawn" or "break"),
                   sessId, attrs)

    def _sendQueuedSessionCommands(self, session):
        """Send on any queued up commands for this session."""
        sessId = (session.applicationId, session.threadId)
        queuedCommands = self._queuedSessionCommands.get(sessId, [])
        try:
            for commandType, args in queuedCommands:
                if commandType == "set":
                    bp = args[0]
                    self.__setSessionBreakpoint(session, bp)
                elif commandType == "remove":
                    bp = args[0]
                    self.__removeSessionBreakpoint(session, bp)
                elif commandType == "update":
                    bp, attrs = args
                    self.__updateSessionBreakpoint(session, bp, attrs)
        finally:
            self._queuedSessionCommands[sessId] = []


class manager:
    def __init__(self):
        self._server_key = None
        self._proxyAddr = ''
        self._proxyPort = 0
        self.proxyClientAddress = ''
        self.proxyClientPort = 0
        self.appManager = appManager(self)
        self.breakpointManager = self.getBreakpointManager()
        self._listener = None

    def getBreakpointManager(self):
        # Allow this to be overridden.
        return breakpointManager()

    def getURIMappings(self):
        # overriden by IDE interface to provide url to local path mapping
        # to the debugger engine
        return []

    def setKey(self, key):
        self._server_key = key
        # key change, recycle the proxy if necessary
        if self._proxyAddr and self._listener:
            self._stopProxy()
            self._initProxy()
    
    def setProxy(self, address, port):
        if self._proxyAddr and self._listener:
            self._stopProxy()
        self._proxyAddr = address
        self._proxyPort = port
        if self._proxyAddr and self._listener:
            self._initProxy()
        
    def _initProxy(self):
        log.debug('manager starting proxy...')
        if not self._proxyPort:
            self._proxyPort = 9001
        if not self._proxyAddr:
            self._proxyAddr = '127.0.0.1'

        try:
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.connect((self._proxyAddr,self._proxyPort))
            command = u'proxyinit -p %d -k %s -m 1' % \
                        (self._listener._port,
                         self._server_key)
            proxy_socket.send(command.encode('utf-8'))
            resp = proxy_socket.recv(1024)
            proxy_socket.close()
            dom = minidom.parseString(resp)
            root = dom.documentElement
            if root.getAttribute('success') == '1':
                self.proxyClientAddress = root.getAttribute('address')
                self.proxyClientPort = int(root.getAttribute('port'))
        except Exception, e:
            self.stop()
            raise DBGPError("the debugger proxy could not be contacted.")

    def _stopProxy(self):
        log.debug('manager stopping proxy...')
        try:
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.connect((self._proxyAddr,self._proxyPort))
            command = u'proxystop -k %s' % self._server_key
            proxy_socket.send(command.encode('utf-8'))
            resp = proxy_socket.recv(1024)
            proxy_socket.close()
            self.proxyClientAddress = ''
            self.proxyClientPort = 0
        except Exception, e:
            # if we cannot stop the proxy when we're stopping, lets let it go
            log.debug('unable to contact proxy to stop proxying')
    
    def listen(self, address, port):
        log.debug('manager starting listener...')
        self._listener = listener(self)
        _address, _port = self._listener.start(address,port)
        if self._proxyAddr:
            self._initProxy()
        return (_address, _port)
    
    def stop(self):
        if not self._listener:
            log.debug('manager stop called, but no listener')
            return
        if self._proxyAddr:
            self._stopProxy()
        log.debug('manager stopping listener...')
        self._listener.stop()
        self._listener = None
    
    def shutdown(self):
        self.stop()
        self.appManager.shutdown()

    def getApplicationList(self):
        return self.appManager.appList.values()
        
    ##################################################################
    # session callback functions
    ##################################################################

    def onConnect(self, session, client, addr):
        # before any communication, we can decide if we want
        # to allow the connection here.  return 0 to deny
        log.info("Connection received from %r:%r",addr[0],addr[1])
        return 1
    
    def initHandler(self, session, init):
        # this is called once during a session, after the connection
        # to provide initialization information.  initNode is a
        # minidom node.  If we have a session key, it will be validated
        # later, and the key doesn't matter for us.
        if self._server_key and not init.getAttribute('session'):
            idekey = init.getAttribute('idekey')
            if idekey != self._server_key:
                session.stop()
                log.info("Session stopped, incorrect key [%s]", idekey)
                return 0
        self.appManager.getApplication(session)
        # XXX notify init listeners
        return 1
    
    def notifyInit(self, session, init):
        # should be overridden
        pass

    def notifyStartup(self, session, init):
        # should be overridden
        pass
