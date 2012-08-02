" Vim syntax file
" Language: Vim Debugger Watch
" Maintainer: Jon Cairns
" Latest Revision: 2 August 2012

if exists("b:current_syntax")
  finish
endif

syn match watchMarker '^\s\+[^|\/]'
syn match watchJoiner '^\s\+[|\/^]' 
syn match watchVarName '\s\zs.\+\ze\s='
syn match watchTypeContainer '=\s\zs\(.*\)\ze\s' contains=watchType,watchSize
syn match watchType '\w' contained
syn match watchSize '\[\d\+\]' contained
syn region watchString start='"' skip='\\"' end='"'


hi def link watchMarker Special
hi def link watchType Type
hi def link watchString String
hi def link watchVarName Identifier
hi def link watchJoiner Structure
hi def link watchSize Number
