" Vim syntax file
" Language: Vim Debugger Watch
" Maintainer: Jon Cairns
" Latest Revision: 2 August 2012

if exists("b:current_syntax")
  finish
endif

syn match debuggerStatusIdentifier '^Status:'
syn match debuggerStatusBreak '\s\zsbreak\ze'
syn match debuggerStatusStart '\s\zsrunning\ze'
syn match debuggerStatusStop '\s\zs\(stopped\|stopping\)\ze'
syn region debuggerStatusInfo start='Press' end='information.'

hi def link debuggerStatusIdentifier Type
hi def link debuggerStatusStop Special
hi def link debuggerStatusBreak Error
hi def link debuggerStatusStart Constant
hi def link debuggerStatusInfo Comment
