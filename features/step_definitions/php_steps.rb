Given "I start the debugger with the PHP script $script" do |script|
  fullscript = Dir.getwd + "/" + script
  $vim.server.remote_send ":python debugger.run()<CR>"
  sleep 1
  system %Q{XDEBUG_CONFIG="idekey=something" /usr/bin/env php #{fullscript} &}
end
