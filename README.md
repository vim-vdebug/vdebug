# Vdebug

[![Build Status](https://travis-ci.org/vim-vdebug/vdebug.png?branch=master)](https://travis-ci.org/vim-vdebug/vdebug)

## Introduction

Vdebug is a new, fast, powerful debugger client for Vim. It's multi-language,
and has been tested with PHP, Python, Ruby, Perl, Tcl and NodeJS. It interfaces
with **any** debugger that faithfully uses the DBGP protocol, such as Xdebug
for PHP. There are step-by-step instructions for setting up debugging with all
of the aforementioned languages in the Vim help file that comes with Vdebug.

It builds on the experience gained through the legacy of the Xdebug Vim script
originally created by Seung Woo Shin and extended by so many others, but it's a
total rebuild to allow for a nicer interface and support of new features.

It's written in Python, and has an object-oriented interface that is easy to
extend and can even be used from the command-line. It even has unit tests
covering some of the more critical parts of the code.

## Installation

**Requirements**:

* Vim compiled with Python 3 support, tabs and signs (for Debian/Ubuntu this is
  provided in the vim-nox package)
* A programming language that has a DBGP debugger, e.g. PHP, Python, Ruby,
  Perl, NodeJS, Tcl...

The actual installation is no different than for any other Vim plugin, you can

* install manually: Clone or download a tarball of the plugin and move its
  content in your `~/.vim/` directory.  You should call `:helptags ~/.vim/doc`
  to generate the necessary help tags afterwards.
* use Pathogen: Clone this repository to your `~/.vim/bundle` directory and
  `:call pathogen#helptags()` afterwards.
* use your favorite plugin manager: Put the respective instruction in your init
  file and update your plugins afterwards.  For Vundle this would be `Plugin
  'vim-vdebug/vdebug'` and `:PluginInstall`.

### Python 2

When you are stuck on a machine with only `+python` (Python 2) support you can
use the latest [1.5][5] release.

## Usage

There is *extensive* help provided in the form of a Vim help file. This goes
through absolutely everything, from installation to configuration, setting up
debuggers for various languages, explanation of the interface, options, remote
server debugging and more.

To get this help, type:

```
:help Vdebug
```

### Quick guide

Set up any DBGP protocol debugger, e.g. Xdebug. (See :help VdebugSetUp). Start
Vdebug with `<F5>`, which will make it wait for an incoming connection. Run the
script you want to debug, with the debugging engine enabled. A new tab will
open with the debugging interface.

Once in debugging mode, the following default mappings are available:

* `<F5>`: start/run (to next breakpoint/end of script)
* `<F2>`: step over
* `<F3>`: step into
* `<F4>`: step out
* `<F6>`: stop debugging (kills script)
* `<F7>`: detach script from debugger
* `<F9>`: run to cursor
* `<F10>`: toggle line breakpoint
* `<F11>`: show context variables (e.g. after "eval")
* `<F12>`: evaluate variable under cursor
* `:Breakpoint <type> <args>`: set a breakpoint of any type (see :help
  VdebugBreakpoints)
* `:VdebugEval <code>`: evaluate some code and display the result
* `<Leader>e`: evaluate the expression under visual highlight and display the
  result

To stop debugging, press `<F6>`. Press it again to close the debugger
interface.

If you can't get a connection, then chances are you need to spend a bit of time
setting up your environment. Type `:help Vdebug` for more information.

## Getting help

If you're having trouble with Vdebug in any way, here are the steps you can
take to get help (in the right order):

1. [Check the issues][3] to see whether it's already come up.
2. Visit the **#vdebug** irc channel on freenode, someone is normally there.
3. [Open a new issue.][4]

## Debugging

If you have a problem, and would like to see what's going on under the hood or
raise an issue, it's best to create a log file. You can do this by setting
these options before you start debugging:

```vim
:VdebugOpt debug_file ~/vdebug.log
:VdebugOpt debug_file_level 2
```

Then start debugging, and you can follow what's added to the log file as you
go. It shows the communication between the debugging engine and Vdebug.

If you're creating an issue then it's probably best to upload a log as a Gist,
as it can be pretty large.

## Contributing

I gladly accept contributions to the code. Just fork the repository, make your
changes and open a pull request with detail about your changes. There are a
couple of conditions:

* The tests must pass (see below)
* Your commit messages should follow the [rules outlined here][2]

## Tests

The tests use `unittest` and `mock`, which are both part of the stdlib in
Python 3. To run the tests, run `python3 -m unittest discover` in the top
directory of the plugin

## Licence

This plugin is released under the [MIT License][1].

[1]: https://raw.github.com/vim-vdebug/vdebug/master/LICENCE
[2]: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
[3]: https://github.com/vim-vdebug/vdebug/issues/
[4]: https://github.com/vim-vdebug/vdebug/issues/new
[5]: https://github.com/vim-vdebug/vdebug/releases/tag/v1.5.2
