" DBGp client: a remote debugger interface to the DBGp protocol
"
" Script Info and Documentation  {{{
"=============================================================================
"    Copyright: Copyright (C) 2007 Sam Ghods
"      License:	The MIT License
"				
"				Permission is hereby granted, free of charge, to any person obtaining
"				a copy of this software and associated documentation files
"				(the "Software"), to deal in the Software without restriction,
"				including without limitation the rights to use, copy, modify,
"				merge, publish, distribute, sublicense, and/or sell copies of the
"				Software, and to permit persons to whom the Software is furnished
"				to do so, subject to the following conditions:
"				
"				The above copyright notice and this permission notice shall be included
"				in all copies or substantial portions of the Software.
"				
"				THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
"				OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
"				MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"				IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
"				CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
"				TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
"				SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
" Name Of File: debugger.vim, debugger.py
"  Description: remote debugger interface to DBGp protocol
"   Maintainer: Sam Ghods <sam <at> box.net>
"  Last Change: June 18, 2007
"          URL: http://www.vim.org/scripts/script.php?script_id=1929
"      Version: 1.1.1
"               Originally written by Seung Woo Shin <segv <at> sayclub.com>
"               The original script is located at:
"				http://www.vim.org/scripts/script.php?script_id=1152
"        Usage: N.B.: For a complete tutorial on how to setup this script,
"               please visit:
"               http://tech.blog.box.net/2007/06/20/how-to-debug-php-with-vim-and-xdebug-on-linux/
"               -----
"
"               This file should reside in the plugins directory along
"               with debugger.py and be automatically sourced.
"               
"               By default, the script expects the debugging engine to connect
"               on port 9000. You can change this with the g:debuggerPort
"               variable by putting the following line your vimrc:
"
"                 let g:debuggerPort = 10001
"
"               where 10001 is the new port number you want the server to
"               connect to.
"
"               There are three maximum limits you can set referring to the
"               properties (variables) returned by the debugging engine.
"
"               g:debuggerMaxChildren (default 32): The max number of array or
"               object children to initially retrieve per variable.
"               For example:
"
"                 let g:debuggerMaxChildren = 64
"
"               g:debuggerMaxData (default 1024 bytes): The max amount of
"               variable data to retrieve.
"               For example:
"
"                 let g:debuggerMaxData = 2048
"
"               g:debuggerMaxDepth (default 1): The maximum depth that the
"               debugger engine may return when sending arrays, hashs or
"               object structures to the IDE.
"               For example:
"
"                 let g:debuggerMaxDepth = 10
"
"               Finally, if you use the Mini Buffer Explorer vim plugin,
"               minibufexpl.vim, running the debugger may mess up your window
"               setup. As a result the script has support to close and open
"               the explorer when you enter and quit debugging sessions. To
"               enable this support, add the following line to your vimrc:
"
"                 let g:debuggerMiniBufExpl = 1
"
"      History: 1.1.1 o Added a check so the script doesn't load if python is
"                     not compiled in. (Contributed by Lars Becker.)
"               1.1   o Added vim variable to change port.
"                     o You can now put debugger.py in either runtime directory
"                     or the home directory.
"                     o Added to ability to change max children, data and depth
"                     settings.
"                     o Made it so stack_get wouldn't be called if the debugger
"                     has already stopped.
"                     o Added support for minibufexpl.vim.
"                     o License added.
"               1.0   o Initial release on December 7, 2004
"      
" Known Issues: The code is designed for the DBGp protocol, but it has only been
" 				tested with XDebug 2.0RC4. If anyone would like to contribute patches
" 				to get it working with other DBGp software, I would be happy
" 				to implement them.
"
" 				Sometimes things go a little crazy... breakpoints don't show
" 				up, too many windows are created / not enough are closed, and
" 				so on... if you can actually find a set of solidly
" 				reproducible steps that lead to a bug, please do e-mail <sam
" 				<at> box.net> and I will take a look.
" 
"         Todo: Compatibility for other DBGp engines.
"
"         		Add a status line/window which constantly shows what the current
"         		status of the debugger is. (starting, break, stopped, etc.)
"
"=============================================================================
" }}}

" Do not source this script when python is not compiled in.
if !has("python")
    finish
endif

" Load debugger.py either from the runtime directory (usually
" /usr/local/share/vim/vim71/plugin/ if you're running Vim 7.1) or from the
" home vim directory (usually ~/.vim/plugin/).
if filereadable($VIMRUNTIME."/plugin/debugger.py")
  pyfile $VIMRUNTIME/plugin/debugger.py
elseif filereadable($HOME."/.vim/plugin/debugger.py")
  pyfile $HOME/.vim/plugin/debugger.py
else
  call confirm('debugger.vim: Unable to find debugger.py. Place it in either your home vim directory or in the Vim runtime directory.', 'OK')
endif

map <F1> :python debugger_resize()<cr>
map <F2> :python debugger_command('step_into')<cr>
map <F3> :python debugger_command('step_over')<cr>
map <F4> :python debugger_command('step_out')<cr>

map <Leader>dr :python debugger_resize()<cr>
map <Leader>di :python debugger_command('step_into')<cr>
map <Leader>do :python debugger_command('step_over')<cr>
map <Leader>dt :python debugger_command('step_out')<cr>

nnoremap ,e :python debugger_watch_input("eval")<cr>A

map <F5> :python debugger_run()<cr>
map <F6> :python debugger_quit()<cr>

map <F7> :python debugger_command('step_into')<cr>
map <F8> :python debugger_command('step_over')<cr>
map <F9> :python debugger_command('step_out')<cr>

map <F11> :python debugger_context()<cr>
map <F12> :python debugger_property()<cr>
map <F11> :python debugger_watch_input("context_get")<cr>A<cr>
map <F12> :python debugger_watch_input("property_get", '<cword>')<cr>A<cr>

hi DbgCurrent term=reverse ctermfg=White ctermbg=Red gui=reverse
hi DbgBreakPt term=reverse ctermfg=White ctermbg=Green gui=reverse

command! -nargs=? Bp python debugger_mark('<args>')
command! -nargs=0 Up python debugger_up()
command! -nargs=0 Dn python debugger_down()
sign define current text=->  texthl=DbgCurrent linehl=DbgCurrent
sign define breakpt text=B>  texthl=DbgBreakPt linehl=DbgBreakPt

if !exists('g:debuggerPort')
  let g:debuggerPort = 9000
endif 
if !exists('g:debuggerMaxChildren')
  let g:debuggerMaxChildren = 32
endif
if !exists('g:debuggerMaxData')
  let g:debuggerMaxData = 1024
endif
if !exists('g:debuggerMaxDepth')
  let g:debuggerMaxDepth = 1
endif
if !exists('g:debuggerMiniBufExpl')
  let g:debuggerMiniBufExpl = 0
endif
python debugger_init(1)
