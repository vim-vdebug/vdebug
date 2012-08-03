" Vim syntax file
" Language: Vim Debugger Watch
" Maintainer: Jon Cairns
" Latest Revision: 2 August 2012

if exists("b:current_syntax")
  finish
endif

syn match debuggerStackNumberGroup '^\[\d\+\]' contains=debuggerStackNumber
syn match debuggerStackName '\s\zs\S\+\ze\s'
syn region debuggerStackFile start=+\s\s.+ end=+$+ contains=debuggerStackLineNumber
syn match debuggerStackLineNumber ':\zs\d\+\ze' contained

hi def link debuggerStackNumberGroup Type
hi def link debuggerStackFile String
hi def link debuggerStackLineNumber Special
