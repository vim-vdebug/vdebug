import vim

class Window:

  def write(self, msg):
    """ append last """
    """if type(msg) is unicode:
      msg =
      unicodedata.normalize('NFKD',msg).encode('ascii','ignore')"""
    self.prepare()
    if self.firstwrite == 1:
      self.firstwrite = 0
      self.buffer[:] = str(msg).split('\n')
    else:
      self.buffer.append(str(msg).split('\n'))
    self.command('normal G')
    #self.window.cursor = (len(self.buffer), 1)

  def insert(self, msg, lineno = None, overwrite = False, allowEmpty = False):
    """ insert into current position in buffer"""
    if len(msg) == 0 and allowEmpty == False:
      return
    self.prepare()
    if self.firstwrite == 1:
      self.firstwrite = 0
      self.buffer[:] = str(msg).split('\n')
    else:
      if lineno == None:
        (lineno, rol) = vim.current.window.cursor
      remaining_buffer = str(msg).split('\n')
      if overwrite:
        lfrom = lineno + 1
      else:
        lfrom = lineno
      remaining_buffer.extend(self.buffer[lfrom:])
      del self.buffer[lineno:]
      for line in remaining_buffer:
        self.buffer.append(line)

  def create(self, method = 'new'):
    """ create window """
    vim.command('silent ' + method + ' ' + self.name)
    #if self.name != 'LOG___WINDOW':
    vim.command("setlocal buftype=nofile")
    self.buffer = vim.current.buffer
    self.width  = int( vim.eval("winwidth(0)")  )
    self.height = int( vim.eval("winheight(0)") )
    self.on_create()
  def destroy(self):
    """ destroy window """
    if self.buffer == None or len(dir(self.buffer)) == 0:
      return
    #if self.name == 'LOG___WINDOW':
    #  self.command('hide')
    #else:
    self.command('bdelete ' + self.name)
    self.firstwrite = 1
  def clean(self):
    """ clean all datas in buffer """
    self.prepare()
    self.buffer[:] = []
    self.firstwrite = 1
  def command(self, cmd):
    """ go to my window & execute command """
    self.prepare()
    winnr = self.getwinnr()
    if winnr != int(vim.eval("winnr()")):
      vim.command(str(winnr) + 'wincmd w')
    vim.command(cmd)

