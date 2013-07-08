require 'vimrunner'
Before do
  $vim = Vimrunner.start

  Dir.mkdir 'tmpspace' unless Dir.exists? 'tmpspace'
  Dir.chdir 'tmpspace'

  # Or, start a GUI instance:
  # vim = Vimrunner.start_gvim

  # Setup your plugin in the Vim instance
  plugin_path = File.expand_path('../../..', __FILE__)
  $vim.add_plugin(plugin_path, 'plugin/vdebug.vim')

  # The returned value is the Client available in the tests.
  $vim
end

After do
  $vim.kill if $vim
  Dir.chdir '..'
  system "rm -r tmpspace"
end
