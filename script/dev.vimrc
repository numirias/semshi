"A minimal vimrc for development

syntax on
set nocompatible
colorscheme zellner

set noswapfile
set hidden

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


let $SEMSHI_LOG_FILE = '/tmp/semshi.log'
let $SEMSHI_LOG_LEVEL = 'DEBUG'
