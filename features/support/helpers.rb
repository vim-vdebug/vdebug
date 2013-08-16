require 'shellwords'

module VdebugHelper
  def vdebug
    @vdebug ||= Vdebug.new vim
  end

  def vim
    @vim ||= Vimrunner.start
  end

  def kill_vim
    if @vim
      @vim.kill
      @vim = nil
      @vdebug = nil
    end
  end
end

module ScriptRunner
  def run_php_script(path)
    fork_and_run 'php', Shellwords.escape(path)
  end

  def fork_and_run(bin, argstr)
    fork do
      exec %Q{XDEBUG_CONFIG="idekey=something" /usr/bin/env #{bin} #{argstr}}
      exit!
    end
    sleep 0.5
  end
end

World(VdebugHelper)
World(ScriptRunner)
