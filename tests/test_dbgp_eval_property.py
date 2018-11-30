import unittest
import vdebug.dbgp
import xml.etree.ElementTree as ET

class EvalPropertyTest(unittest.TestCase):
    def __get_eval_property(self,xml_string,code,lang):
        xml = ET.fromstring(xml_string)
        firstnode = xml[0]
        return vdebug.dbgp.EvalProperty(firstnode,code,lang)

    def test_numeric_keys(self):
        prop = self.__get_eval_property(\
            """<?xml version="1.0" encoding="iso-8859-1"?>
<response xmlns="urn:debugger_protocol_v1" xmlns:xdebug="http://xdebug.org/dbgp/xdebug" command="eval" transaction_id="13">
    <property
      address="140722906708544" type="array"
      children="1" numchildren="2" page="0" pagesize="32">
        <property
          name="0" address="140022315302704"
          type="array" children="1" numchildren="1"></property>
        <property
          name="key" address="140022315307008"
          type="array" children="1" numchildren="1"></property>
    </property>
</response>
""", '$testarr', 'php')

        self.assertEqual(prop.display_name,'$testarr')
        self.assertEqual(prop.value,'')
        self.assertEqual(prop.type,'array')
        self.assertEqual(prop.depth,0)
        self.assertTrue(prop.has_children)
        self.assertEqual(prop.child_count(),2)

        self.assertEqual(prop.children[0].type,'array')
        self.assertEqual(prop.children[0].display_name,'$testarr[0]')

        self.assertEqual(prop.children[1].type,'array')
        self.assertEqual(prop.children[1].display_name,"$testarr['key']")

    def test_non_unicode_value(self):
        prop = self.__get_eval_property(\
            """<?xml version="1.0" encoding="iso-8859-1"?>
<response xmlns="urn:debugger_protocol_v1" xmlns:xdebug="http://xdebug.org/dbgp/xdebug" command="context_get" transaction_id="8" context="0">
    <property name="$value" fullname="$value" type="string" size="68" encoding="base64"><![CDATA[AAAAAAHa86Gey+29BQAKYWJ1c2VIOWU0MzI5NjEtMzg5Zi00NmJiLWEwZDUtZDM4MGI1ODY5YzRinsCwBJzAsASSpHM=]]></property>
</response>
""", '$value', 'php')

        self.assertEqual(prop.display_name,'$value')
        self.assertEqual(len(prop.value),94)
        self.assertEqual(prop.type,'string')
