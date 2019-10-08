hi def semshiLocal           ctermfg=209 guifg=#ff875f
hi def semshiGlobal          ctermfg=214 guifg=#ffaf00
hi def semshiImported        ctermfg=214 guifg=#ffaf00 cterm=bold gui=bold
hi def semshiParameter       ctermfg=75  guifg=#5fafff
hi def semshiParameterUnused ctermfg=117 guifg=#87d7ff cterm=underline gui=underline
hi def semshiFree            ctermfg=218 guifg=#ffafd7
hi def semshiBuiltin         ctermfg=207 guifg=#ff5fff
hi def semshiAttribute       ctermfg=49  guifg=#00ffaf
hi def semshiSelf            ctermfg=249 guifg=#b2b2b2
hi def semshiUnresolved      ctermfg=226 guifg=#ffff00 cterm=underline gui=underline
hi def semshiSelected        ctermfg=231 guifg=#ffffff ctermbg=161 guibg=#d7005f

hi def semshiErrorSign       ctermfg=231 guifg=#ffffff ctermbg=160 guibg=#d70000
hi def semshiErrorChar       ctermfg=231 guifg=#ffffff ctermbg=160 guibg=#d70000
sign define semshiError text=E> texthl=semshiErrorSign


" These options can't be initialized in the Python plugin since they must be
" known immediately.
let g:semshi#filetypes = get(g:, 'semshi#filetypes', ['python'])
let g:semshi#simplify_markup = get(g:, 'semshi#simplify_markup', v:true)
let g:semshi#no_default_builtin_highlight = get(g:, 'semshi#no_default_builtin_highlight', v:true)

function! s:simplify_markup()
    autocmd FileType python call s:simplify_markup_extra()

    " For python-syntax plugin
    let g:python_highlight_operators = 0
endfunction

function! s:simplify_markup_extra()
    hi link pythonConditional pythonStatement
    hi link pythonImport pythonStatement
    hi link pythonInclude pythonStatement
    hi link pythonRaiseFromStatement pythonStatement
    hi link pythonDecorator pythonStatement
    hi link pythonException pythonStatement
    hi link pythonConditional pythonStatement
    hi link pythonRepeat pythonStatement
endfunction

function! s:disable_builtin_highlights()
    autocmd FileType python call s:remove_builtin_extra()
    let g:python_no_builtin_highlight = 1
    hi link pythonBuiltin NONE
    let g:python_no_exception_highlight = 1
    hi link pythonExceptions NONE
    hi link pythonAttribute NONE
    hi link pythonDecoratorName NONE

    " For python-syntax plugin
    let g:python_highlight_class_vars = 0
    let g:python_highlight_builtins = 0
    let g:python_highlight_exceptions = 0
    hi link pythonDottedName NONE
endfunction

function! s:remove_builtin_extra()
    syn keyword pythonKeyword True False None
    hi link pythonKeyword pythonNumber
endfunction

function! s:filetype_changed()
    let l:ft = expand('<amatch>')
    if index(g:semshi#filetypes, l:ft) != -1
        if !get(b:, 'semshi_attached', v:false)
            Semshi enable
        endif
    else
        if get(b:, 'semshi_attached', v:false)
            Semshi disable
        endif
    endif
endfunction

function! semshi#buffer_attach()
    if get(b:, 'semshi_attached', v:false)
        return
    endif
    let b:semshi_attached = v:true
    augroup SemshiEvents
        autocmd BufEnter <buffer> call SemshiBufEnter(+expand('<abuf>'), line('w0'), line('w$'))
        autocmd BufLeave <buffer> call SemshiBufLeave()
        autocmd VimResized <buffer> call SemshiVimResized(line('w0'), line('w$'))
        autocmd TextChanged <buffer> call SemshiTextChanged()
        autocmd TextChangedI <buffer> call SemshiTextChanged()
        autocmd CursorMoved <buffer> call SemshiCursorMoved(line('w0'), line('w$'))
        autocmd CursorMovedI <buffer> call SemshiCursorMoved(line('w0'), line('w$'))
    augroup END
    call SemshiBufEnter(bufnr('%'), line('w0'), line('w$'))
endfunction

function! semshi#buffer_detach()
    let b:semshi_attached = v:false
    augroup SemshiEvents
        autocmd! BufEnter <buffer>
        autocmd! BufLeave <buffer>
        autocmd! VimResized <buffer>
        autocmd! TextChanged <buffer>
        autocmd! TextChangedI <buffer>
        autocmd! CursorMoved <buffer>
        autocmd! CursorMovedI <buffer>
    augroup END
endfunction

function! semshi#init()
    if g:semshi#no_default_builtin_highlight
        call s:disable_builtin_highlights()
    endif
    if g:semshi#simplify_markup
        call s:simplify_markup()
    endif

    autocmd FileType * call s:filetype_changed()
    autocmd BufWipeout * call SemshiBufWipeout(+expand('<abuf>'))
endfunction

call semshi#init()
