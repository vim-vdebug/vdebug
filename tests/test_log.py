from . import setup
import sys
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


class FileLoggerTest(unittest.TestCase):

    filename = '/tmp/vdebug-test-log-file'
    level = 2
    if sys.version_info[0] == 3:
        open_name = 'builtins.open'
    elif sys.version_info[0] == 2:
        open_name = '__builtin__.open'

    def setUp(self):
        self.logger = vdebug.log.FileLogger(self.level, self.filename)

    def test_log_opens_file(self):
        with mock.patch(self.open_name, mock.mock_open()) as mocked_open:
            self.logger.log('text', self.level)
        mocked_open.assert_called_once_with(self.filename, 'w')
        handle = mocked_open()
        handle.write.assert_called_once()
        handle.flush.assert_called_once()

    def test_log_with_open_file(self):
        handle = mock.Mock()
        self.logger.f = handle
        with mock.patch(self.open_name, mock.mock_open()) as mocked_open:
            self.logger.log('text', self.level)
        mocked_open.assert_not_called()
        handle.write.assert_called_once()
        handle.flush.assert_called_once()

    def test_shutdown_without_file(self):
        with mock.patch(self.open_name, mock.mock_open()) as mocked_open:
            self.logger.shutdown()
        handle = mocked_open()
        handle.close.assert_not_called()

    def test_shutdown_with_file(self):
        with mock.patch(self.open_name, mock.mock_open()) as mocked_open:
            self.logger.log('text', self.level)
            self.logger.shutdown()
        mocked_open.assert_called_once_with(self.filename, 'w')
        handle = mocked_open()
        handle.close.assert_called_once_with()
