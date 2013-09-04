class Vdebug
  class BufferNotFound < StandardError; end;

  attr_reader :vim

  def initialize(vim)
    @vim = vim
  end

  def start_listening
    clear_buffer_cache!
    vim.server.remote_send ":python debugger.run()<CR>"
    sleep 1
  end

  def step_over
    vim.command 'python debugger.step_over()'
  end

  # Retrieve a hash with the buffer names (values) and numbers (keys)
  def buffers
    @buffers ||= fetch_buffers
  end

  # Do this when you want to refresh the buffer list
  def clear_buffer_cache!
    @buffers = nil
  end

  # Has the vdebug GUI been opened?
  def gui_open?
    names = buffers.values
    %w[DebuggerStack DebuggerStatus DebuggerWatch].all? { |b|
      names.include? b
    }
  end

  def running?
    gui_open? && connected?
  end

  def connected?
     is_connected = vim.command(
       "python print debugger.runner.is_alive()"
     )
     is_connected == "True"
  end

  def watch_window_content
    fetch_buffer_content 'DebuggerWatch'
  end

  def status_window_content
    fetch_buffer_content 'DebuggerStatus'
  end

protected
  def fetch_buffer_content(name)
    bufnum = buffers.invert.fetch(name)
    vim.echo(%Q{join(getbufline(#{bufnum}, 1, "$"), "\\n")})
  rescue KeyError
    raise BufferNotFound, "#{name} buffer not found"
  end

  def fetch_buffers
    buffer_string = vim.command('buffers')
    names = buffer_string.split("\n").collect do |bufline|
      matches = /\A\s*(\d+).*"([^"]+)"/.match(bufline)
      [matches[1].to_i, matches[2]] if matches
    end
    Hash[names.compact]
  end
end
