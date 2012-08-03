import sys
sys.path.append('../plugin/python')
import unittest
import dbgp
import xml

class ResponseTest(unittest.TestCase): 
    """Test the response class in the dbgp module."""

    def test_get_cmd(self):
        """Test that the get_cmd() method returns the command"""
        cmd = "status"
        res = dbgp.Response("",cmd,"")
        assert res.get_cmd() == cmd

    def test_get_cmd_args(self):
        """Test that the get_cmd_args() method return command arguments"""
        cmd_args = "-a abcd"
        res = dbgp.Response("","",cmd_args)
        assert res.get_cmd_args() == cmd_args

    def test_as_string(self):
        """Test that the as_string() method returns the
        raw response string"""
        response = "<?xml..."
        res = dbgp.Response(response,"","")
        assert res.as_string() == response

    def test_as_xml_is_element(self):
        """Test that the as_xml() method returns an XML
        element"""
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1"
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug" 
            command="status" transaction_id="1" status="starting" 
            reason="ok"></response>"""
        res = dbgp.Response(response,"","")
        self.assertIsInstance(res.as_xml(),xml.etree.ElementTree.Element)

    def test_error_tag_raises_exception(self):
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1" 
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug"
            command="stack_get" transaction_id="4"><error
            code="5"><message><![CDATA[command is not available]]>
            </message></error></response>"""
        re = "command is not available"
        self.assertRaisesRegexp(dbgp.DBGPError,re,dbgp.Response,response,"","")

class StatusResponseTest(unittest.TestCase): 
    """Test the behaviour of the StatusResponse class."""
    def test_string_is_status_text(self):
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1"
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug" 
            command="status" transaction_id="1" status="starting" 
            reason="ok"></response>"""
        res = dbgp.StatusResponse(response,"","")
        assert str(res) == "starting"

class FeatureResponseTest(unittest.TestCase): 
    """Test the behaviour of the FeatureResponse class."""
    def test_feature_is_supported(self):
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1" 
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug" 
            command="feature_get" transaction_id="2" 
            feature_name="max_depth" supported="1"><![CDATA[1]]></response>"""
        res = dbgp.FeatureGetResponse(response,"","")
        assert res.is_supported() == 1

    def test_feature_is_not_supported(self):
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1" 
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug" 
            command="feature_get" transaction_id="2" 
            feature_name="max_depth" supported="0"><![CDATA[0]]></response>"""
        res = dbgp.FeatureGetResponse(response,"","")
        assert res.is_supported() == 0

class StackGetTest(unittest.TestCase): 
    """Test the behaviour of the StackGetResponse class."""
    def test_string_is_status_text(self):
        response = """<?xml version="1.0" encoding="iso-8859-1"?>
            <response xmlns="urn:debugger_protocol_v1" 
            xmlns:xdebug="http://xdebug.org/dbgp/xdebug"
            command="stack_get" transaction_id="8">
                <stack where="{main}" level="0" type="file"
                filename="file:///usr/local/bin/cake" lineno="4">
                </stack>
            </response>"""
        res = dbgp.StackGetResponse(response,"","")
        stack = res.get_stack()
        assert stack[0].get('filename') == "file:///usr/local/bin/cake"
        assert len(stack) == 1
