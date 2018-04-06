hi semshiBuiltin ctermfg=207
hi semshiGlobal ctermfg=214
hi semshiFree ctermfg=225 cterm=underline
hi semshiUnresolved ctermfg=226 cterm=underline
hi semshiParam ctermfg=75
hi semshiSelf ctermfg=249
hi semshiImported ctermfg=214 cterm=bold
hi semshiLocal ctermfg=209
hi semshiAttr ctermfg=49
hi semshiMarked ctermbg=161 ctermfg=white cterm=bold


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
