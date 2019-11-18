" Vdebug: Powerful, fast, multi-language debugger client for Vim.
"
" Script Info  {{{
"=============================================================================
"    Copyright: Copyright (C) 2012 Jon Cairns
"      Licence: The MIT Licence (see LICENCE file)
" Name Of File: vdebug.vim
"  Description: Multi-language debugger client for Vim (PHP, Ruby, Python,
"               Perl, NodeJS)
"   Maintainer: Jon Cairns <jon at joncairns.com>
"      Version: 2.0.0
"               Inspired by the Xdebug plugin, which was originally written by
"               Seung Woo Shin <segv <at> sayclub.com> and extended by many
"               others.
"        Usage: Use :help Vdebug for information on how to configure and use
"               this script, or visit the Github page
"               https://github.com/vim-vdebug/vdebug.
"
"=============================================================================
" }}}

" avoid double loading of vdebug
if exists('g:is_vdebug_loaded')
    finish
endif

" Set a special flag used only by this plugin for preventing doubly
" loading the script.
let g:is_vdebug_loaded = 1

" Do not source this script when python is not compiled in.
if !has('python3')
    echomsg ':python3 is not available, vdebug will not be loaded.'
    finish
endif

" Nice characters get screwed up on windows
if has('win32') || has('win64')
    let g:vdebug_force_ascii = 1
elseif has('multi_byte') == 0
    let g:vdebug_force_ascii = 1
else
    let g:vdebug_force_ascii = 0
end

if !exists('g:vdebug_options')
    let g:vdebug_options = {}
endif

if !exists('g:vdebug_keymap')
    let g:vdebug_keymap = {}
endif

if !exists('g:vdebug_features')
    let g:vdebug_features = {}
endif

if !exists('g:vdebug_leader_key')
    let g:vdebug_leader_key = ''
endif

let g:vdebug_keymap_defaults = {
\    'run' : '<F5>',
\    'run_to_cursor' : '<F9>',
\    'step_over' : '<F2>',
\    'step_into' : '<F3>',
\    'step_out' : '<F4>',
\    'close' : '<F6>',
\    'detach' : '<F7>',
\    'set_breakpoint' : '<F10>',
\    'get_context' : '<F11>',
\    'eval_under_cursor' : '<F12>',
\    'eval_visual' : '<Leader>e'
\}

let g:vdebug_options_defaults = {
\    'port' : 9000,
\    'timeout' : 20,
\    'server' : '',
\    'on_close' : 'stop',
\    'break_on_open' : 1,
\    'ide_key' : '',
\    'debug_window_level' : 0,
\    'debug_file_level' : 0,
\    'debug_file' : '',
\    'path_maps' : {},
\    'watch_window_style' : 'expanded',
\    'marker_default' : '⬦',
\    'marker_closed_tree' : '▸',
\    'marker_open_tree' : '▾',
\    'sign_breakpoint' : '▷',
\    'sign_current' : '▶',
\    'sign_disabled': '▌▌',
\    'continuous_mode'  : 1,
\    'background_listener' : 1,
\    'auto_start' : 1,
\    'simplified_status': 1,
\    'layout': 'vertical',
\}

" Different symbols for non unicode Vims
if g:vdebug_force_ascii == 1
    let g:vdebug_options_defaults['marker_default'] = '*'
    let g:vdebug_options_defaults['marker_closed_tree'] = '+'
    let g:vdebug_options_defaults['marker_open_tree'] = '-'
    let g:vdebug_options_defaults['sign_breakpoint'] = 'B>'
    let g:vdebug_options_defaults['sign_current'] = '->'
    let g:vdebug_options_defaults['sign_disabled'] = 'B|'
endif

" Create the top dog
python3 import vdebug.debugger_interface
python3 debugger = vdebug.debugger_interface.DebuggerInterface()

" Commands
command! -nargs=? VdebugChangeStack python3 debugger.change_stack(<q-args>)
command! -nargs=? -complete=customlist,s:BreakpointTypes Breakpoint python3 debugger.cycle_breakpoint(<q-args>)
command! -nargs=? -complete=customlist,s:BreakpointTypes SetBreakpoint python3 debugger.set_breakpoint(<q-args>)
command! VdebugStart python3 debugger.run()
command! -nargs=? BreakpointRemove python3 debugger.remove_breakpoint(<q-args>)
command! BreakpointWindow python3 debugger.toggle_breakpoint_window()
command! -nargs=? -bang VdebugEval python3 debugger.handle_eval('<bang>', <q-args>)
command! -nargs=+ -complete=customlist,s:OptionNames VdebugOpt :call Vdebug_set_option(<f-args>)
command! -nargs=+ VdebugPathMap :call Vdebug_path_map(<f-args>)
command! -nargs=+ VdebugAddPathMap :call Vdebug_add_path_map(<f-args>)
command! -nargs=? VdebugTrace python3 debugger.handle_trace(<q-args>)
command! -nargs=? BreakpointStatus python3 debugger.breakpoint_status(<q-args>)

if hlexists('DbgCurrentLine') == 0
    hi default DbgCurrentLine term=reverse ctermfg=White ctermbg=Red guifg=#ffffff guibg=#ff0000
end
if hlexists('DbgCurrentSign') == 0
    hi default DbgCurrentSign term=reverse ctermfg=White ctermbg=Red guifg=#ffffff guibg=#ff0000
end
if hlexists('DbgBreakptLine') == 0
    hi default DbgBreakptLine term=reverse ctermfg=White ctermbg=Green guifg=#ffffff guibg=#00ff00
end
if hlexists('DbgBreakptSign') == 0
    hi default DbgBreakptSign term=reverse ctermfg=White ctermbg=Green guifg=#ffffff guibg=#00ff00
end

" Signs and highlighted lines for breakpoints, etc.
function! s:DefineSigns()
    exe 'sign define breakpt text=' . g:vdebug_options['sign_breakpoint'] . ' texthl=DbgBreakptSign linehl=DbgBreakptLine'
    exe 'sign define current text=' . g:vdebug_options['sign_current'] . ' texthl=DbgCurrentSign linehl=DbgCurrentLine'
    exe 'sign define breakpt_dis text=' . g:vdebug_options['sign_disabled'] . ' texthl=DbgDisabledSign linehl=DbgDisabledLine'
endfunction

function! s:BreakpointTypes(A,L,P)
    let arg_to_cursor = strpart(a:L,11,a:P)
    let space_idx = stridx(arg_to_cursor,' ')
    if space_idx == -1
        return filter(['conditional ','exception ','return ','call ','watch '],'v:val =~ "^".a:A.".*"')
    else
        return []
    endif
endfunction

function! s:HandleEval(bang,code)
    let code = escape(a:code,'"')
    if strlen(a:bang)
        execute 'python3 debugger.save_eval("'.code.'")'
    endif
    if strlen(a:code)
        execute 'python3 debugger.handle_eval("'.code.'")'
    endif
endfunction

" Reload options dictionary, by merging with default options.
"
" This should be called if you want to update the options after vdebug has
" been loaded.
function! Vdebug_load_options(options)
    " Merge options with defaults
    let g:vdebug_options = extend(g:vdebug_options_defaults, a:options)

    " Override with single defined params ie. g:vdebug_options_port
    let single_defined_params = s:Vdebug_get_options()
    let g:vdebug_options = extend(g:vdebug_options, single_defined_params)

    call s:DefineSigns()
    python3 debugger.reload_options()
endfunction

" Get options defined outside of the vdebug_options dictionary
"
" This helps for when users might want to define a single option by itself
" without needing the dictionary ie. vdebug_options_port = 9000
function! s:Vdebug_get_options()
    let param_namespace = 'g:vdebug_options_'
    let param_namespace_len = strlen(param_namespace)

    " Get the paramter names and concat the g:vdebug_options namespace
    let parameters = map(keys(g:vdebug_options_defaults), 'param_namespace.v:val')

    " Only use the defined parameters
    let existing_params = filter(parameters, 'exists(v:val)')

    " put into a dictionary for use with extend()
    let params = {}
    for name in existing_params
      let val = eval(name)

      " Remove g:vdebug_options namespace from param
      let name = strpart(name, param_namespace_len)
      let params[name] = val
    endfor
    if !empty(params)
      echoerr 'Deprication Warning: The options g:vdebug_options_* are depricated.  Please use the g:vdebug_options dictionary.'
    endif
    return params
endfunction

" Assign keymappings, and merge with defaults.
"
" This should be called if you want to update the keymappings after vdebug has
" been loaded.
function! Vdebug_load_keymaps(keymaps)
    " Unmap existing keys, if needed
    " the keys should in theory exist because they are part of the defaults
    if has_key(g:vdebug_keymap, 'run')
        exe 'silent! nunmap '.g:vdebug_keymap['run']
    endif
    if has_key(g:vdebug_keymap, 'close')
        exe 'silent! nunmap '.g:vdebug_keymap['close']
    endif
    if has_key(g:vdebug_keymap, 'set_breakpoint')
        exe 'silent! nunmap '.g:vdebug_keymap['set_breakpoint']
    endif
    if has_key(g:vdebug_keymap, 'eval_visual')
        exe 'silent! vunmap '.g:vdebug_keymap['eval_visual']
    endif

    " Merge keymaps with defaults
    let g:vdebug_keymap = extend(g:vdebug_keymap_defaults, a:keymaps)

    " Mappings allowed in non-debug mode
    " XXX: don't use keymaps not found in g:vdebug_keymap_defaults
    exe 'noremap '.g:vdebug_keymap['run'].' :python3 debugger.run()<cr>'
    exe 'noremap '.g:vdebug_keymap['close'].' :python3 debugger.close()<cr>'
    exe 'noremap '.g:vdebug_keymap['set_breakpoint'].' :python3 debugger.set_breakpoint()<cr>'

    " Exceptional case for visual evaluation
    exe 'vnoremap '.g:vdebug_keymap['eval_visual'].' :python3 debugger.handle_visual_eval()<cr>'
    python3 debugger.reload_keymappings()
endfunction

function! s:OptionNames(A,L,P)
    let arg_to_cursor = strpart(a:L,10,a:P)
    let space_idx = stridx(arg_to_cursor,' ')
    if space_idx == -1
        return filter(keys(g:vdebug_options_defaults),'v:val =~ a:A')
    else
        let opt_name = strpart(arg_to_cursor,0,space_idx)
        if has_key(g:vdebug_options,opt_name)
            return [g:vdebug_options[opt_name]]
        else
            return []
        endif
    endif
endfunction

function! Vdebug_set_option(option, ...)
    if ! a:0
        let g:vdebug_options[a:option]
        return
    endif
    if a:option == 'path_maps'
        echomsg 'use :VdebugAddPathMap to add extra or :VdebugPathMap to set new'
        return
    elseif a:option == 'window_commands'
        echomsg 'update window_commands in your vimrc please'
        return
    elseif a:option == 'window_arrangement'
        echomsg 'update window_arrangement in your vimrc please'
        return
    endif
    echomsg 'Setting vdebug option "' . a:option . '" to: ' . a:1
    let g:vdebug_options[a:option] = a:1
    call s:DefineSigns()
    python3 debugger.reload_options()
endfunction

function! Vdebug_add_path_map(from, to)
    echomsg 'Adding vdebug path map "{' . a:from . ':' . a:to . '}"'
    let g:vdebug_options['path_maps'] = extend(g:vdebug_options['path_maps'], {a:from: a:to})
    python3 debugger.reload_options()
endfunction

function! Vdebug_path_map(from, to)
    echomsg 'Setting vdebug path maps to "{' . a:from . ':' . a:to . '}"'
    let g:vdebug_options['path_maps'] = {a:from: a:to}
    python3 debugger.reload_options()
endfunction

function! Vdebug_get_visual_selection()
  let [lnum1, col1] = getpos("'<")[1:2]
  let [lnum2, col2] = getpos("'>")[1:2]
  let lines = getline(lnum1, lnum2)
  let lines[-1] = lines[-1][: col2 - 1]
  let lines[0] = lines[0][col1 - 1:]
  return join(lines, "\n")
endfunction

function! Vdebug_edit(filename)
    try
        execute 'buffer' fnameescape(a:filename)
    catch /^Vim\%((\a\+)\)\=:E94/
        execute 'silent view' fnameescape(a:filename)
    endtry
endfunction

function! Vdebug_statusline()
    return pyeval('debugger.status_for_statusline()')
endfunction

augroup Vdebug
augroup END
augroup VdebugOut
autocmd VimLeavePre * python3 debugger.close()
augroup END

call Vdebug_load_options(g:vdebug_options)
call Vdebug_load_keymaps(g:vdebug_keymap)
