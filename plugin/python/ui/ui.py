
class Ui():
    """Ui layer which manages the Vim windows.
    """

    def __init__(self):
        self.__open()

    def __del__(self):
        self.__close()

    def __open(self):

