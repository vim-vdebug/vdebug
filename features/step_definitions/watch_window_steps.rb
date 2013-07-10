Then "the watch window should show the variable $var" do |var|
  vdebug.watch_window_content.should include var
end
