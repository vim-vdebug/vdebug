import time

class Logger:
    """ Abstract class for all logger implementations.
    
    Concrete classes will log messages using various methods,
    e.g. write to a file.
    """

    (ERROR,INFO,DEBUG) = ("ERROR","Info","Debug")
    debug_level = ERROR

    def __init__(self,debug_level):
        pass

    def log(self, string, level):
        """ Log a message """
        pass

    def shutdown(self):
        """ Action to perform when closing the logger """
        pass

    def time(self):
        """ Get a nicely formatted time string """
        return time.strftime("%a %d %Y %H:%M:%S", \
                time.localtime())

    def format(self,string,level):
        """ Format the error message in a standard way """
        return "- [" + level + "] " + \
                "{" + self.time() + "} " + \
                string


class WindowLogger(Logger):
    """ Log messages to a window.

    The window object is passed in on construction, but
    only created if a message is written.
    """
    def __init__(self,debug_level,window):
        self.window = window
        self.debug_level = debug_level

    def shutdown(self):
        if self.window is not None:
            self.window.destroy()

    def log(self, string, level):
        if not self.window.is_open:
            self.window.create()
        self.window.write(\
                self.format(string,level))


class FileLogger(Logger):
    def log(self, string, level):
        print "Not yet implemented!"

class Log:

    logger = None

    def __init__(self,string,level = Logger.INFO):
        Log.log(string,level)

    @classmethod
    def log(cls, string, level = Logger.INFO):
        cls.get_logger().log(string,level)

    @classmethod
    def get_logger(cls):
        if cls.logger is None:
            raise LogError, "No Logger object has been \
assigned"
        return cls.logger

    @classmethod
    def set_logger(cls, logger):
        cls.logger = logger

    @classmethod
    def shutdown(cls):
        cls.get_logger().shutdown()

class LogError(Exception):
    pass

