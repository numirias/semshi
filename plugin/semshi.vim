hi semshiLocal      ctermfg=209 guifg=#ff875f
hi semshiGlobal     ctermfg=214 guifg=#ffaf00
hi semshiImported   ctermfg=214 guifg=#ffaf00 cterm=bold gui=bold
hi semshiParameter  ctermfg=75  guifg=#5fafff
hi semshiFree       ctermfg=218 guifg=#ffafd7
hi semshiBuiltin    ctermfg=207 guifg=#ff5fff
hi semshiAttribute  ctermfg=49  guifg=#00ffaf
hi semshiSelf       ctermfg=249 guifg=#b2b2b2
hi semshiUnresolved ctermfg=226 guifg=#ffff00 cterm=underline gui=underline
hi semshiSelected   ctermfg=231 guifg=#ffffff ctermbg=161 guibg=#d7005f


hi semshiError ctermfg=white ctermbg=160
sign define semshiError text=E> texthl=semshiError


if !exists('g:semshi#active')
    let g:semshi#active = 1
endif

if !exists('g:semshi#excluded_hl_groups')
    let g:semshi#excluded_hl_groups = ['local']
endif

if !exists('g:semshi#mark_original_node')
    let g:semshi#mark_original_node = 0
endif
