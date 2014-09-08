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

import socket, string, sys, os, re
import threading, select
import base64
from xml.dom import minidom

import dbgp.listcmd as listcmd
from dbgp.common import *

try:
    import logging
except ImportError:
    from dbgp import _logging as logging

log = logging.getLogger("dbgp.server")
#log.setLevel(logging.DEBUG)

# the host class implements commands that the host can send
# to the debugger target
class session:
    def __init__(self, sessionHost):
        self._socket = None
        self._clientAddr = None
        self._cmdthread = None
        self._stop = 0
        self._transaction_id = 0
        self._sessionHost = sessionHost

    def _cmdloop(self):
        # called periodicaly by the debugger while the script is
        # running.  This checks for data on the socket, responds
        # to it if any, and deals with stream IO.
        error_count = 0
        try:
            while self._socket and not self._stop:
                try:
                    #log.debug('checking for data on the socket')
                    (input, output, exceptional) = \
                            select.select([self._socket],[],[], .1)
                    if input:
                        #log.debug('handling data available on socket')
                        self._handleIncoming()
                except Exception, e:
                    error_count += 1
                    if error_count >= 5:
                        log.exception("had 5 session cmdloop exceptions - aborting the session")
                        break
                    log.exception("session cmdloop exception - sending session stop command")
                    msg = ("""<?xml version="1.0" encoding="UTF-8" ?>\n"""
                           + """<response xmlns="urn:debugger_protocol_v1" """
                           + """command="stop" status="stopped" reason="ok" """
                           + """transaction_id="%r"/>""") % self._transaction_id
                    self._dispatch(len(msg), msg)
        finally:
            self._cmdthread = None
            if self._socket:
                self._socket.close()
                self._socket = None
        log.info("session cmdloop done")

    def start(self, socket, clientAddr):
        if not self._sessionHost.onConnect(self, socket, clientAddr):
            socket.close()
            return 0
        self._socket = socket
        self._clientAddr = clientAddr
        # create a new thread and initiate a debugger session
        if not self._cmdthread or not self._cmdthread.isAlive():
            self._cmdthread = threading.Thread(target = self._cmdloop)
            self._cmdthread.start()
        return 1

    def stop(self):
        if self._socket:
            self.sendCommand(['stop'])
        log.debug('received stop command')
        self._stop = 1

    def _dispatch(self, size, response):
        if size != len(response):
            raise "Data length is not correct %d != %d" % (size,len(response))
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
            text = base64.decodestring(text)
            self._sessionHost.outputHandler(self, type,text)
        elif packetType == 'response':
            command = root.getAttribute('command')
            if command == 'stop' or command == 'detach':
                log.debug("command %s recieved", command)
                self._stop = 1
                if self._socket:
                    try:
                        self._socket.close()
                    finally:
                        self._socket = None
            self._sessionHost.responseHandler(self, root)
        elif packetType == 'init':
            # get our init information
            self._sessionHost.initHandler(self, root)
        else:
            print root.ownerDocument.toprettyxml()

    def _handleIncoming(self):
        data = ''
        while self._socket and not self._stop:
            newdata = self._socket.recv(1024)
            if not newdata: # EOF on socket, break (see bug 48688).
                self._stop = 1
                break
            data += newdata
            log.debug("socket recv: [%s]", data)
            while data:
                eop = data.find('\0')
                if eop < 0:
                    break
                size = long(data[:eop])
                data = data[eop+1:] # skip \0
                sizeLeft = size - len(data) + 1
                while sizeLeft > 0:
                    newdata = self._socket.recv(sizeLeft)
                    log.debug("socket recv: [%s]", newdata)
                    if not newdata: # EOF on socket, break (see bug 48688).
                        self._stop = 1
                        break
                    data += newdata
                    sizeLeft = sizeLeft - len(newdata)
                
                if self._stop:
                    break
                response = data[:size]
                data = data[size+1:] # skip \0
                log.debug("dispatch message: %s", response)
                self._dispatch(size,response)
            if not data:
                break

    _re_escape = re.compile(r'(["\'\\])')
    def sendCommand(self, argv, data = None):
        if not self._socket:
            raise DBGPError('Socket disconnected', ERROR_EXCEPTION)
        self._transaction_id = self._transaction_id + 1

        argv += ['-i', str(self._transaction_id)]
        if data:
            argv += ['--', base64.encodestring(data).strip()]
            
        # if the args need quoting, it will happen here, argv2line doesn't
        # handle it all
        # cmdline = listcmd.argv2line(argv)
        escapedArgs = []
        for arg in argv:
            # we must escape any quotes in the argument
            arg = self._re_escape.sub(r'\\\1', arg)
            if ' ' in arg or '"' in arg or "'" in arg or '\\' in arg:
                arg = '"'+arg+'"'
            escapedArgs.append(str(arg))
        cmdline = ' '.join(escapedArgs)
        try:
            #print "sendCommand: %s"% cmdline
            log.debug("sendCommand: %s", cmdline)
            self._socket.sendall(cmdline+'\0')
            #log.debug("sendCommand: %s DONE", cmdline)
        except socket.error, e:
            log.error("session sendCommand socket error %r", e)
            self._stop = 1
        return self._transaction_id

# this is the host server that accepts connections
# and kicks off host threads to handle those connections
class listener:
    def __init__(self, sessionHost):
        self._address = None
        self._port = None
        self._thread = None
        self._stop = 0
        self._session_host = sessionHost
        self._totalConnections = 0

    def checkListening(self):
        return self._thread and self._thread.isAlive()

    def start(self, address, port):
        # stop any existing listener
        if self.checkListening():
            if self._address == address and self._port == port:
                log.error("Host server already listening")
                return
            self.stop()
        
        log.info("Start listening on %s:%d.", address or "127.0.0.1", port)
        self._address = address
        self._port = port
        self._stop = 0
        # if bind raises an exception, dont start
        # the listen thread
        self._bind()
        self._thread = threading.Thread(target = self._listen)
        self._thread.start()
        return (self._address, self._port)

    def stop(self):
        if self.checkListening():
            log.debug('listener.stop attempt to close server')
            port = self._port
            if port is None:
                return
            addr = self._address
            if not addr:
                addr = '127.0.0.1'
            self._stop = 1
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((addr, port))
                s.close()
            except socket.error, details:
                log.error("The host listener could not cancel the "+\
                      "listener %d:%r", port, details)
        else:
            log.debug('listener.stop was not listening')

    def _bind(self):
        try:
            self._server = socket.socket(socket.AF_INET,
                                         socket.SOCK_STREAM)

            # Try to re-use a server port if possible this is necessary on linux
            # (and solaris) in order to start listening AGAIN on the same socket
            # that we were listening on before, if the listener was stopped.

            # XXX the below setsocketopt is bad for multiuser systems (Windows
            # and Mac?). The first server instance will always get all debugger
            # sessions for the defined port. This is only an issue if the port
            # is not set to zero in prefs.

            # For Linux, the bind call will fail if there is an existing socket
            # already listening on this port (so it does not present a security
            # problem on Linux).
            if sys.platform.startswith("linux"):
                self._server.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR,
                    self._server.getsockopt(socket.SOL_SOCKET,
                                            socket.SO_REUSEADDR) | 1)
            
            self._server.bind((self._address, self._port))
            if not self._port:
                addr = self._server.getsockname()
                self._port = addr[1]
        except socket.error, details:
            errmsg = "the debugger could not bind on port %d." % self._port
            self._port = 0
            self._server = None
            raise DBGPError(errmsg)

    def _listen(self):
        try:
            self._server.listen(5)
        except socket.error, details:
            log.exception("Unable to listen on socket connection")
            raise DBGPError("the debugger could not start listening on port %d." % self._port)
        try:
            while not self._stop:
                (client, addr) = self._server.accept()
                if self._stop:
                    break
                log.info("server connection: %r", addr)
                self.startNewSession(client, addr)
                self._totalConnections = self._totalConnections + 1
        except socket.error, details:
            raise DBGPError("the debugger could not accept new connection.")
        log.debug('listener._listen thread shutting down')
        try:
            self._server.close()
        except socket.error, details:
            raise DBGPError("the debugger could could not be closed.")
        self._server = None
        self._stop = 0
        self._address = None
        self._port = None

    def startNewSession(self, client, addr):
        # start a new thread that is the host connection
        # for this debugger session
        sessionHost = session(self._session_host)
        sessionHost.start(client, addr)

