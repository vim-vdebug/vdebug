" Powerful, fast, multi-language debugger client for Vim.
"
" Script Info and Documentation  {{{
"=============================================================================
"    Copyright: Copyright (C) 2012 Jon Cairns
"      Licence:	The MIT Licence (see LICENCE file)
" Name Of File: vdebug.vim
"  Description: Multi-language debugger client for Vim
"   Maintainer: Jon Cairns <jon at joncairns.com>
"  Last Change: June 18, 2007
"      Version: 1.0
"               Inspired by the Xdebug plugin, which was originally written by 
"               Seung Woo Shin <segv <at> sayclub.com> and extended by many
"               others.
"        Usage: Use :help Vdebug for information on how to configure and use
"               this script, or visit the Github page http://github.com/joonty/vdebug.
"
"=============================================================================
" }}}

" Do not source this script when python is not compiled in.
if !has("python")
    finish
endif

" Load start_vdebug.py either from the runtime directory (usually
" /usr/local/share/vim/vim71/plugin/ if you're running Vim 7.1) or from the
" home vim directory (usually ~/.vim/plugin/).
if filereadable($VIMRUNTIME."/plugin/python/start_vdebug.py")
  pyfile $VIMRUNTIME/plugin/start_vdebug.py
elseif filereadable($HOME."/.vim/plugin/python/start_vdebug.py")
  pyfile $HOME/.vim/plugin/python/start_vdebug.py
else
  " when we use pathogen for instance
  let $CUR_DIRECTORY=expand("<sfile>:p:h")

  if filereadable($CUR_DIRECTORY."/python/start_vdebug.py")
    pyfile $CUR_DIRECTORY/python/start_vdebug.py
  else
    call confirm('vdebug.vim: Unable to find start_vdebug.py. Place it in either your home vim directory or in the Vim runtime directory.', 'OK')
  endif
endif

python debugger = DebuggerInterface()

if !exists("g:debugger_options")
    let g:debugger_options = {}
endif

if !exists("g:debugger_keymap")
    let g:debugger_keymap = {}
endif

let g:debugger_keymap_defaults = {
\    "run" : "<F5>",
\    "run_to_cursor" : "<F1>",
\    "step_over" : "<F2>",
\    "step_into" : "<F3>",
\    "step_out" : "<F4>",
\    "close" : "<F6>",
\    "set_breakpoint" : "<F8>",
\}

let g:debugger_options_defaults = {
\    "port" : 9000,
\    "timeout" : 30,
\    "server" : 'localhost',
\    "on_close" : 'detach',
\    "ide_key" : '',
\    "debug_window_level" : 0,
\    "debug_file_level" : 2,
\    "debug_file" : "/home/jon/vdebug.log",
\    "remote_path" : "/home/pi/projects",
\    "local_path" : "/home/jon",
\}

let g:debugger_options = extend(g:debugger_options_defaults,g:debugger_options)
let g:debugger_keymap = extend(g:debugger_keymap_defaults,g:debugger_keymap)

for [s:fname, s:key] in items(g:debugger_keymap)
    exe "map ".s:key." :python debugger.".s:fname."()<cr>"
endfor

vnoremap <Leader>e :python debugger.handle_visual_eval()<cr>

command! -nargs=? Breakpoint python debugger.set_breakpoint('<args>')
command! -nargs=? BreakpointRemove python debugger.remove_breakpoint('<args>')
command! BreakpointWindow python debugger.toggle_breakpoint_window()

command! -nargs=? VdebugEval python debugger.handle_eval('<args>')

sign define current text=->  texthl=DbgCurrent linehl=DbgCurrent
sign define breakpt text=B>  texthl=DbgBreakPt linehl=DbgBreakPt

hi DbgCurrent term=reverse ctermfg=White ctermbg=Red gui=reverse
hi DbgBreakPt term=reverse ctermfg=White ctermbg=Green gui=reverse

function! vdebug:get_visual_selection()
  let [lnum1, col1] = getpos("'<")[1:2]
  let [lnum2, col2] = getpos("'>")[1:2]
  let lines = getline(lnum1, lnum2)
  let lines[-1] = lines[-1][: col2 - 1]
  let lines[0] = lines[0][col1 - 1:]
  return join(lines, "\n")
endfunction
