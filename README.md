# Vim-Xdebug

This vim plugin provides a debugger interface to DBGp protocol, and therefore
Xdebug (only tested on Xdebug 2).

This is a fork of [this plugin](http://www.vim.org/scripts/script.php?script_id=1152), which
is a bit buggy, limited is many ways and not maintained anymore.


# Installation

**Requirements**:

  * Vim compiled with Python (2) support
  * DBGp protocol enabled debugging module, such as Xdebug.

## Classic

Clone or download a tarball of the plugin and move its content in your
`~/.vim/` directory.

Your `~/.vim/plugins/` directory should now have two more files: `debugger.py`
and `debugger.vim`.

## Using git and Pathogen

Clone this repository in your `~/.vim/bundle` directory (and yeah, you're done).


# Quick guide

  1. setup Xdebug - or other DBGp enabled server - correctly (with proper remote
     debug option)
  2. press `F5` to make Vim wait for a debugging connection and browse your PHP
     file (you have five seconds to do it once you press `F5`).

     All the currently opened windows will be closed and debugging interface
     will appear.
  3. Once in debugging mode, the following mappings are available:

      * `<F1>`: resizing windows
      * `<F2>`: step into
      * `<F3>`: step over
      * `<F4>`: step out
      * `<F6>`: stop debugging
      * `<F11>`: shows all variables
      * `<F12>`: shows variable on current cursor
      * `,e`: evaluate an expression and display the result
  4. To stop debugging, press `<F6>`


## Notes

 * You'll see some python's exception message. They happen when connection is
   closed, because Xdebug doesn't send message for last file/line information.
 * This plugin doesn't implement all DBGP's features, just the very essential
   parts.


# Contributors

 * Ludovic Pelle <ludovic_pelle AT carpe-hora.com>
 * [Kévin Gomez](https://github.com/K-Phoen) <contact AT kevingomez.fr>
 * Sam Ghods <sam AT box.net>
 * Seung Woo Shin <segv AT sayclub.com>


# Licence

The MIT/Expat licence.
