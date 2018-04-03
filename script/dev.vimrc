"A minimal vimrc for development

syntax on
set nocompatible
colorscheme pax

let &runtimepath.=','.getcwd()

let mapleader = ","

noremap <silent> <S-j> 4j
noremap <silent> <S-k> 4k
noremap <silent> <Leader>q :q<CR>

let $NVIM_RPLUGIN_MANIFEST = './script/rplugin.vim'
