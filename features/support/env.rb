require 'vimrunner'
require_relative "../../rubylib/vdebug"

PHP_INI = File.expand_path('../../../.travis.php.ini', __FILE__)

Before do
  Dir.mkdir 'tmpspace' unless Dir.exists? 'tmpspace'
  Dir.chdir 'tmpspace'

  # Setup plugin in the Vim instance
  plugin_path = File.expand_path('../../..', __FILE__)
  vim.add_plugin(plugin_path, 'plugin/vdebug.vim')
end

After do
  kill_vim
  Dir.chdir '..'
  system "rm -r tmpspace"
end
