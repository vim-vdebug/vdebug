class Window:
    name = "WINDOW"

    def __del__(self):
        self.destroy()

    def on_create(self):
        pass

    def write(self, msg):
        """ Write string in the window """
        pass

    def insert(self, msg, position = None):
        """ Insert a string somewhere in the window """
        pass

    def destroy(self):
        """ Close window """
        pass

    def clean(self):
        """ clean all data in buffer """
        pass
