import sys
sys.path.append('../plugin')
import unittest
from dbgp import Protocol
from mock import MagicMock, patch

class ProtocolTest(unittest.TestCase):      
    """Test the protocol class in the dbgp module."""

    def setUp(self):
        with patch('dbgp.Connection') as c:
            self.c = c.return_value
            self.c.isconnected.return_value = 1
            self.p = Protocol(self.c)

    def test_status_send(self):
        """Test that the status command sends the right format command."""
        self.p.conn.send_msg = MagicMock()
        self.p.status()
        self.p.conn.send_msg.assert_called_once_with('status -i 1')

    def test_status_retval(self):
        """Test that the status command receives a message from the protocol."""
        self.p.conn.recv_msg.return_value = "status_ret"
        status = self.p.status()
        assert status == "status_ret"
