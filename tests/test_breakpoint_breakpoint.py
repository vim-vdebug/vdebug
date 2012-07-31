import sys
sys.path.append('../plugin/python/')
import unittest
import breakpoint
import base64
from mock import Mock

class LineBreakpointTest(unittest.TestCase):

    def test_get_file(self):
        """ Test that the line number is retrievable."""
        ui = None
        file = "/path/to/file"
        line = 1
        bp = breakpoint.LineBreakpoint(ui,file,line)
        assert bp.get_file() == file

    def test_get_line(self):
        """ Test that the line number is retrievable."""
        ui = None
        file = "/path/to/file"
        line = 10
        bp = breakpoint.LineBreakpoint(ui,file,line)
        assert bp.get_line() == line

    def test_get_cmd(self):
        """ Test that the dbgp command is correct."""
        ui = None
        file = "/path/to/file"
        line = 20
        bp = breakpoint.LineBreakpoint(ui,file,line)
        assert bp.get_cmd() == "-t line -f %s -n %i" %(file, line)

    def test_on_add_sets_ui_breakpoint(self):
        """ Test that the breakpoint is placed on the source window."""
        ui = Mock()
        file = "/path/to/file"
        line = 20
        bp = breakpoint.LineBreakpoint(ui,file,line)
        bp.on_add()
        ui.place_breakpoint.assert_called_with(\
                bp.get_id(),\
                file,\
                line)

    def test_on_remove_deletes_ui_breakpoint(self):
        """ Test that the breakpoint is removed from the source window."""
        ui = Mock()
        file = "/path/to/file"
        line = 20
        bp = breakpoint.LineBreakpoint(ui,file,line)
        bp.on_remove()
        ui.remove_breakpoint.assert_called_with(bp.get_id())

class ConditionalBreakpointTest(unittest.TestCase):
    def test_get_cmd(self):
        """ Test that the dbgp command is correct."""
        ui = None
        file = "/path/to/file"
        line = 20
        condition = "$x > 20"
        bp = breakpoint.ConditionalBreakpoint(ui,file,line,condition)
        b64cond = base64.encodestring(condition)
        exp_cmd = "-t conditional -f %s -n %i -- %s" %(file, line, b64cond)
        assert bp.get_cmd() == exp_cmd


class BreakpointTest(unittest.TestCase):

    def test_id_is_unique(self):
        """Test that each Breakpoint has a unique ID.

        Consecutively generated breakpoints should have
        different IDs."""
        bp1 = breakpoint.Breakpoint(None)
        bp2 = breakpoint.Breakpoint(None)

        self.assertNotEqual(bp1.get_id(),bp2.get_id())

    def test_parse_with_line_breakpoint(self):
        """ Test that a LineBreakpoint is created."""
        ui = Mock()
        ret = breakpoint.Breakpoint.parse(ui,"")
        self.assertIsInstance(ret,breakpoint.LineBreakpoint)

    def test_parse_with_conditional_breakpoint(self):
        """ Test that a ConditionalBreakpoint is created."""
        ui = Mock()
        ret = breakpoint.Breakpoint.parse(ui,"conditional $x == 3")
        self.assertIsInstance(ret,breakpoint.ConditionalBreakpoint)
        assert ret.condition == "$x == 3"

    def test_parse_with_conditional_raises_error(self):
        """ Test that an exception is raised with invalid conditional args."""
        ui = Mock()
        args = "conditional"
        re = "Conditional breakpoints require a condition "+\
                "to be specified"
        self.assertRaisesRegexp(breakpoint.BreakpointError,\
                re, breakpoint.Breakpoint.parse, ui, args)

        
