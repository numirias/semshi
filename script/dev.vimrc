"A minimal vimrc for development

syntax on
set nocompatible
colorscheme zellner

set noswapfile
set hidden
set tabstop=8
set shiftwidth=4
set softtabstop=4
set smarttab
set expandtab
set number

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

let g:semshi#error_sign_delay = 0.5

nmap <silent> <leader>rr :Semshi rename<CR>
nmap <silent> <Tab> :Semshi goto name next<CR>
nmap <silent> <S-Tab> :Semshi goto name prev<CR>

nmap <silent> <C-n> :Semshi goto class next<CR>
nmap <silent> <C-p> :Semshi goto class prev<CR>

nmap <silent> <C-a> :Semshi goto function next<CR>
nmap <silent> <C-x> :Semshi goto function prev<CR>

nmap <silent> <leader>ee :Semshi error<CR>
nmap <silent> <leader>ge :Semshi goto error<CR>
