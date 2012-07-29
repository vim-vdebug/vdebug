import time

class Log:

    logger = None

    def __init__(self,string,level = 0):
        Log.log(string,level)

    @classmethod
    def log(cls, string, level = 0):
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

class Logger:
    def log(self, string, level):
        pass

    def shutdown(self):
        pass

class WindowLogger(Logger):
    def __init__(self,window):
        self.window = window

    def shutdown(self):
        if self.window is not None:
            self.window.destroy()

    def log(self, string, level):
        self.window.write(str(time.localtime())+\
                ": "+string)


class FileLogger(Logger):
    def log(self, string, level):
        print "Not yet implemented!"
