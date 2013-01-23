if __name__ == "__main__":
    import sys
    sys.path.append('../plugin/python/')
import unittest2 as unittest
""" Mock vim import """
import vdebug.opts
from vdebug.util import FilePath,FilePathError

class LocalFilePathTest(unittest.TestCase):

    def setUp(self):
        vdebug.opts.Options.set({'path_maps':{}})

    def test_as_local(self):
        filename = "/home/user/some/path"
        file = FilePath(filename)
        self.assertEqual(filename,file.as_local())

    def test_remote_prefix(self):
        prefix = "file://"
        filename = "/home/user/some/path"
        file = FilePath(prefix+filename)
        self.assertEqual(filename,file.as_local())

    def test_quoted(self):
        quoted = "file:///home/user/file%2etcl"
        file = FilePath(quoted)
        self.assertEqual("/home/user/file.tcl",file.as_local())

    def test_win(self):
        quoted = "file:///C:/home/user/file%2etcl"
        file = FilePath(quoted)
        self.assertEqual("C:\\home\\user\\file.tcl",file.as_local())

    def test_as_remote(self):
        filename = "/home/user/some/path"
        file = FilePath(filename)
        self.assertEqual("file://"+filename,file.as_remote())

    def test_eq(self):
        filename = "/home/user/some/path"
        file1 = FilePath(filename)
        file2 = FilePath(filename)
        assert file1 == file2

    def test_eq_false(self):
        filename1 = "/home/user/some/path"
        file1 = FilePath(filename1)
        filename2 = "/home/user/some/other/path"
        file2 = FilePath(filename2)
        self.assertFalse(file1 == file2)

    def test_neq(self):
        filename1 = "/home/user/some/path"
        file1 = FilePath(filename1)
        filename2 = "/home/user/some/other/path"
        file2 = FilePath(filename2)
        assert file1 != file2

    def test_neq_false(self):
        filename = "/home/user/some/path"
        file1 = FilePath(filename)
        file2 = FilePath(filename)
        self.assertFalse(file1 != file2)

    def test_add(self):
        filename = "/home/user/some/path"
        file = FilePath(filename)
        append = "/myfile.txt"
        assert (file + append) == (filename + append)

    def test_add_reverse(self):
        filename = "/user/some/path"
        file = FilePath(filename)
        prepend = "/home/"
        assert (prepend + file) == (prepend + filename)

    def test_empty_file_raises_error(self):
        self.assertRaises(FilePathError,FilePath,"")

class RemotePathTest(unittest.TestCase):
    def setUp(self):
        vdebug.opts.Options.set({'path_maps':{'/remote1/':'/local1/', '/remote2/':'/local2/'}})

    def test_as_local(self):
        filename = "/remote1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local1/path/to/file",file.as_local())

        filename = "/remote2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local2/path/to/file",file.as_local())

    def test_as_local_with_uri(self):
        filename = "file:///remote1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local1/path/to/file",file.as_local())

        filename = "file:///remote2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local2/path/to/file",file.as_local())

    def test_as_local_does_nothing(self):
        filename = "/the/remote/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/the/remote/path/to/file",file.as_local())

    def test_as_remote_with_unix_paths(self):
        filename = "/local1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("file:///remote1/path/to/file",file.as_remote())

        filename = "file:///local2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("file:///remote2/path/to/file",file.as_remote())

    def test_as_remote_with_win_paths(self):
        filename = "C:/local1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("file:///C:/remote1/path/to/file",file.as_remote())

        filename = "file:///C:/local2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("file:///C:/remote2/path/to/file",file.as_remote())

    def test_as_remote_with_backslashed_win_paths(self):
        filename = "C:\\local1\\path\\to\\file"
        file = FilePath(filename)
        self.assertEqual("file:///C:/remote1/path/to/file",file.as_remote())

        filename = "C:\\local2\\path\\to\\file"
        file = FilePath(filename)
        self.assertEqual("file:///C:/remote2/path/to/file",file.as_remote())

        filename = "C:/local2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("C:\\local2\\path\\to\\file",file.as_local())
