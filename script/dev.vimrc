"A minimal vimrc for development

syntax on
set nocompatible
colorscheme pax

let &runtimepath .= ',' . getcwd()
let $NVIM_RPLUGIN_MANIFEST = './script/rplugin.vim'

let mapleader = ','

noremap <silent> <S-j> 4j
noremap <silent> <S-k> 4k
noremap <silent> <Leader>q :q<CR>


function! SynStack()
    if !exists('*synstack')
        return
    endif
    echo map(synstack(line('.'), col('.')), "synIDattr(v:val, 'name')")
endfunc
nnoremap <leader>v :call SynStack()<CR>


function! CustomHighlights()
    syn keyword pythonKeyword True False None
    hi link pythonKeyword pythonNumber

    hi pythonFunction ctermfg=118 cterm=bold
    hi link pythonClass pythonFunction

    hi link pythonImport pythonStatement
    hi link pythonInclude pythonStatement
    hi link pythonRaiseFromStatement pythonStatement
    hi link pythonDecorator pythonStatement
    hi link pythonException pythonStatement
    hi link pythonConditional pythonStatement

    hi link pythonDecoratorName Normal

    hi pythonStrFormat ctermfg=202
    hi link pythonStrFormatting pythonStrFormat
endfunction

autocmd FileType python call CustomHighlights()

let g:python_no_builtin_highlight = 1
let g:python_no_exception_highlight = 1
