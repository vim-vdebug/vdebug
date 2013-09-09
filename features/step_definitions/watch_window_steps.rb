Then "the watch window should show the variable $var" do |var|
  vdebug.watch_window_content.should include var
end

Then "the watch window variable $var should be $value" do |var, value|
  vdebug.watch_vars[var].should == value
end
