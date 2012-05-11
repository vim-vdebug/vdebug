# Vim-Xdebug

This vim plugin provides a debugger interface to DBGp protocol, and therefore
Xdebug (only tested on Xdebug 2).

This is a fork of [this plugin](https://github.com/ludovicPelle/vim-xdebug), 
which in itself is a fork of [this plugin](http://www.vim.org/scripts/script.php?script_id=1152), which
is a bit buggy, limited is many ways and not maintained anymore.

# Changes

* Open the whole debugger session in a new tab, so that your carefully configured windows don't get messed up. When you end the session the whole tab closes.
* The watch window now clears each time a new request is made, so that it doesn't get confusing.
* Better code folding in the watch window
* The default depth of data to retrieve is now configurable, so that you can look deeper into arrays/objects
* Hit `<CR>` (return key) on an array or object in the watch window, and a new request is made to view deeper into the tree. You can go as deep as possible. Then hit `<F11>` to show the whole context again.
* A new "command" window shows the list of commands made to the debugger, and you can hit `<CR>` on any of them to re-run it. You can also type in commands and `<CR>` will execute them.
* When the debugger session ends, no longer do you get an ugly exception. Instead, you get a nice message telling you that it's closed.
* Windows are better arranged (I think).
* Toggle variable for debug mode.


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

## Using vundle

Add this to your `~/.vimrc` file:

```vim
Bundle 'joonty/vim-xdebug.git'
```

# Quick guide

  1. setup Xdebug - or other DBGp enabled server - correctly (with proper remote
     debug option)
  2. press `F5` to make Vim wait for a debugging connection and browse your PHP
     file (it will wait for 30 seconds, to give you plenty of time to run your program).

     All the currently opened windows will be closed and debugging interface
     will appear.
  3. Once in debugging mode, the following mappings are available:

      * `<F1>`: set breakpoint
      * `<F2>`: step into
      * `<F3>`: step over
      * `<F4>`: step out
      * `<F6>`: stop debugging
      * `<F11>`: shows all variables
      * `<F12>`: shows variable on current cursor
      * `,e`: evaluate an expression and display the result
  4. To stop debugging, press `<F6>`


# Contributors

 * Jon Cairns <jon AT joncairns.com>
 * Ludovic Pelle <ludovic_pelle AT carpe-hora.com>
 * [Kévin Gomez](https://github.com/K-Phoen) <contact AT kevingomez.fr>
 * Sam Ghods <sam AT box.net>
 * Seung Woo Shin <segv AT sayclub.com>


# Licence

The MIT/Expat licence.
