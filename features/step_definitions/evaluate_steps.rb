When(/^I evaluate "(.*)"$/) do |expr|
  vdebug.evaluate expr
end

When(/^I evaluate "(.*)" with VdebugEval!$/) do |expr|
  vdebug.evaluate! expr
end

When "I run VdebugEval without any arguments" do
  vdebug.evaluate
end
