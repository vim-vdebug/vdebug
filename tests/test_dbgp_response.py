import sys
sys.path.append('../plugin')
import unittest
from dbgp import Response
import xml

class ResponseTest(unittest.TestCase):      
    """Test the response class in the dbgp module."""

    def test_get_cmd(self):
        """Test that the get_cmd() method returns the command"""
        cmd = "status"
        res = Response("",cmd,"")
        assert res.get_cmd() == cmd

    def test_get_cmd_args(self):
        """Test that the get_cmd_args() method return command arguments"""
        cmd_args = "-a abcd"
        res = Response("","",cmd_args)
        assert res.get_cmd_args() == cmd_args

    def test_as_string(self):
        """Test that the as_string() method returns the
        raw response string"""
        response = "<?xml..."
        res = Response(response,"","")
        assert res.as_string() == response

    def test_as_xml_is_element(self):
        """Test that the as_xml() method returns an XML
        element"""
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1"
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug" 
            command="status" transaction_id="1" status="starting" 
            reason="ok"></response>"""
        res = Response(response,"","")
        self.assertIsInstance(res.as_xml(),xml.etree.ElementTree.Element)
