class Ui():
    """Abstract for the UI, used by the debugger
    """
    watchwin = None
    stackwin = None
    logwin = None
    sourcewin = None

    def __init__(self):
        self.is_open = False

    def __del__(self):
        self.close()

    def open(self):
        pass

    def say(self,string):
        pass

    def close(self):
        pass

    def log(self):
        pass
