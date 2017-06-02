from . import setup
import unittest
import mock
import vdebug.log


class WindowLoggerTest(unittest.TestCase):

    def setUp(self):
        self.window = mock.Mock()
        self.level = 2
        self.logger = vdebug.log.WindowLogger(self.level, self.window)

    def _log_tester(self, window_open, call_level, text='dummy text'):
        self.window.is_open = window_open
        ret = self.logger.log(text, call_level)
        self.assertIsNone(ret)

    def test_log_with_same_level_and_open_window(self):
        self._log_tester(True, self.level)
        self.window.create.assert_not_called()
        self.window.write.assert_called_once()

    def test_log_with_higher_level_and_open_window(self):
        self._log_tester(True, self.level+1)
        self.window.create.assert_not_called()
        self.window.write.assert_not_called()

    def test_log_with_lower_level_and_open_window(self):
        self._log_tester(True, self.level-1)
        self.window.create.assert_not_called()
        self.window.write.assert_called_once()

    def test_log_with_same_level_and_no_window(self):
        self._log_tester(False, self.level)
        self.window.create.assert_called_once()
        self.window.write.assert_called_once()

    def test_log_with_higher_level_and_no_window(self):
        self._log_tester(False, self.level+1)
        self.window.create.assert_not_called()
        self.window.write.assert_not_called()

    def test_log_with_lower_level_and_no_window(self):
        self._log_tester(False, self.level-1)
        self.window.create.assert_called_once()
        self.window.write.assert_called_once()

    def test_shutdown(self):
        self.logger.shutdown()
        self.assertFalse(self.window.is_open)
