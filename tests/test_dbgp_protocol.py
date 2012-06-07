import sys
sys.path.append('../plugin')
import unittest
from dbgp import Protocol
from mock import MagicMock, patch

class ProtocolTest(unittest.TestCase):      
    """Test the protocol class in the dbgp module."""

    init_msg = """<?xml version="1.0"
        encoding="iso-8859-1"?>\n<init
        xmlns="urn:debugger_protocol_v1"
        xmlns:xdebug="http://xdebug.org/dbgp/xdebug"
        fileuri="file:///usr/local/bin/cake" language="PHP"
        protocol_version="1.0" appid="30130"
        idekey="netbeans-xdebug"><engine
        version="2.2.0"><![CDATA[Xdebug]]></engine><author><![CDATA[Derick
        Rethans]]></author><url><![CDATA[http://xdebug.org]]></url><copyright><![CDATA[Copyright
        (c) 2002-2012 by Derick
        Rethans]]></copyright></init>"""

    def setUp(self):
        with patch('dbgp.Connection') as c:
            self.c = c.return_value
            self.c.recv_msg.return_value = self.init_msg
            self.c.isconnected.return_value = 1
            self.p = Protocol(self.c)

    def test_status_send_adds_trans_id(self):
        """Test that the status command sends the right
        format command and adds a transaction ID"""
        self.p.conn.send_msg = MagicMock()
        self.p.status()
        self.p.conn.send_msg.assert_called_once_with('status -i 1')

    def test_status_retval(self):
        """Test that the status command receives a message from the protocol."""
        self.p.conn.recv_msg.return_value = "status_ret"
        status_res = self.p.status()
        assert status_res.as_string() == "status_ret"
