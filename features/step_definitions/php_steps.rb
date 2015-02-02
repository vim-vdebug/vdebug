Given "I start the debugger with the PHP script $script" do |script|
  vdebug.start_listening
  full_script_path = Dir.getwd + "/" + script
  run_php_script full_script_path
  (1..15).each do |n|
    if vdebug.running?
      break
    end
    sleep 1
  end
  vdebug.running?.should be(true), "Error, vdebug is not running\nVIM messages: #{vdebug.messages}"
end
