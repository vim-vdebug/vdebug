import sys
sys.path.append('../plugin/python')
import unittest
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

    def test_as_remote(self):
        filename = "/home/user/some/path"
        file = FilePath(filename)
        self.assertEqual(filename,file.as_remote())

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

def RemotePathTest(self):
    def setUp(self):
        vdebug.opts.Options.set({'path_maps':{'/remote1/':'/local1/', '/remote2/':'/local2'}})

    def test_as_local(self):
        filename = "/remote1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local1/path/to/file",file)

        filename = "/remote2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/local2/path/to/file",file)

    def test_as_remote(self):
        filename = "/local1/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/remote1/path/to/file",file)

        filename = "/local2/path/to/file"
        file = FilePath(filename)
        self.assertEqual("/remote2/path/to/file",file)
