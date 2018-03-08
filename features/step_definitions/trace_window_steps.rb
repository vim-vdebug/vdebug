When(/^I trace "(.*)"$/) do |expr|
  vdebug.trace expr
  sleep 1
end

Then "the trace window should show $text" do |text|
  vdebug.clear_buffer_cache!
  vdebug.trace_window_content.should include text
end

