# Vdebug

Vdebug is a new, fast, powerful debugger client for Vim. It's multi-language,
and has been tested with PHP, Python, Ruby and Perl. It interfaces with **any**
debugger that faithfully uses the DBGP protocol, such as Xdebug for PHP. 

It builds on the experience gained through the legacy of the Xdebug Vim script 
originally created by Seung Woo Shin and extended by so many others, but it's a
total rebuild to allow for a nicer interface and support of new features.

It's written in Python, and has an object-oriented interface that is easy to extend 
and can even be used from the command-line.

# How to use

There is *extensive* help provided in the form of a Vim help file. This goes
through absolutely everything, from installation to configuration, setting up
debuggers for various languages, explanation of the interface, options, remote
server debugging and more.

To get this help, type:

```
:help Vdebug
```

after installing the plugin.

# Installation

**Requirements**:

  * Vim compiled with Python 2 support, tabs and signs
  * A programming language that has a DBGP debugger, e.g. PHP, Python, Ruby,
    Perl, Tcl...

## Classic

Clone or download a tarball of the plugin and move its content in your
`~/.vim/` directory.

Your `~/.vim/plugins/` directory should now contain vdebug.vim and a directory
called "python".

## Using git and Pathogen

Clone this repository in your `~/.vim/bundle` directory

## Using vundle

Add this to your `~/.vimrc` file:

```vim
Bundle 'joonty/vdebug.git'
```

Then, from the command line, run:

```bash
vim +BundleInstall +qall
```

# Quick guide

Set up any DBGP protocol debugger, e.g. Xdebug. (See :help VdebugSetUp). Start Vdebug with `<F5>`, which will make it wait for an incoming connection. Run the script you want to debug, with the debugging engine enabled. A new tab will open with the debugging interface.

Once in debugging mode, the following default mappings are available:

 * `<F1>`: run to cursor
 * `<F2>`: step over
 * `<F3>`: step into
 * `<F4>`: step out
 * `<F5>`: run (to next breakpoint/end of script)
 * `<F6>`: stop debugging
 * `<F10>`: set line breakpoint
 * `:Breakpoint <type> <args>`: set a breakpoint of any type (see :help
    VdebugBreakpoints)
 * `:DebuggerEval <code>`: evaluate some code and display the result
 * `<Leader>e`: evaluate the expression under visual highlight and display the result

To stop debugging, press `<F6>`. Press it again to close the debugger interface.

# Licence

This plugin is released under the [MIT License][6].

[1]: https://raw.github.com/joonty/vdebug/master/LICENSE
