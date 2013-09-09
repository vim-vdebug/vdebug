Then "the first item on the stack should show the file $file" do |file|
  vdebug.stack.first[:file].should include file
end

Then "the first item on the stack should show line $line" do |line|
  vdebug.stack.first[:line].should == line
end
