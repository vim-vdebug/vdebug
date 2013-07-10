When "I step over" do
  vdebug.step_over
  vdebug.running?.should be(true), 'Vdebug is not running'
end
