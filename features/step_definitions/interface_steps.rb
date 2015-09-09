Then "the last message should be $message" do |message|
  sleep 2
  vdebug.last_error.should eq(message)
end
