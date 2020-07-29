# Semshi

[![Build Status](https://travis-ci.org/numirias/semshi.svg?branch=master)](https://travis-ci.org/numirias/semshi)
[![codecov](https://codecov.io/gh/numirias/semshi/branch/master/graph/badge.svg)](https://codecov.io/gh/numirias/semshi)
![Python Versions](https://img.shields.io/badge/python-3.5,%203.6,%203.7,%203.8-blue.svg)

Semshi provides semantic highlighting for Python in Neovim.

Unlike regex-based syntax highlighters, Semshi understands Python code and performs static analysis as you type. It builds a syntax tree and symbol tables to highlight names based on their scope and context. This makes code easier to read and lets you quickly identify missing imports, unused arguments, misspelled names, and more.

| With Semshi | Without Semshi |
| --- | --- |
| ![After](https://i.imgur.com/rDBSM8s.png) | ![Before](https://i.imgur.com/t40TNZ6.png) |

In the above example, you can easily distinguish arguments (blue), instance attributes (teal), globals (orange), unresolved globals (yellow underlined), etc. Also, Semshi understands that the first `list` is assigned locally, while the default highlighter still shows it as builtin.

## Features

- Different highlighting of locals, globals, imports, used and unused function parameters, builtins, attributes, free and unresolved names.

- Scope-aware marking and renaming of related nodes.

  ![Renaming](https://i.imgur.com/5zWRFyg.gif)

- Indication of syntax errors.

  ![Syntax errors](https://i.imgur.com/tCj9myJ.gif)

- Jumping between classes, functions and related names.

## Installation

- You need Neovim with Python 3 support (`:echo has("python3")`). To install the Python provider run:

      pip3 install pynvim --upgrade 
    
- Add `numirias/semshi` via your plugin manager. If you're using [vim-plug](https://github.com/junegunn/vim-plug), add... 

      Plug 'numirias/semshi', { 'do': ':UpdateRemotePlugins' }
      
  ...and run `:PlugInstall`.

- You may also need to run `:UpdateRemotePlugins` to update the plugin manifest.

- Using [deoplete.nvim](https://github.com/Shougo/deoplete.nvim)? [Make sure it doesn't slow down Semshi.](#semshi-is-slow-together-with-deopletenvim)

## Configuration

### Options

You can set these options in your vimrc (`~/.config/nvim/init.vim`):

| Option | Default | Description |
| --- | --- | --- |
| `g:semshi#filetypes` | `['python']` | List of file types on which to enable Semshi automatically. |
| `g:semshi#excluded_hl_groups` | `['local']` | List of highlight groups not to highlight. Choose from `local`, `unresolved`, `attribute`, `builtin`, `free`, `global`, `parameter`, `parameterUnused`, `self`, `imported`. (It's recommended to keep `local` in the list because highlighting all locals in a large file can cause performance issues.) |
| `g:semshi#mark_selected_nodes ` | `1` | Mark selected nodes (those with the same name and scope as the one under the cursor). Set to `2` to highlight the node currently under the cursor, too. |
| `g:semshi#no_default_builtin_highlight` | `v:true` | Disable highlighting of builtins (`list`, `len`, etc.) by Vim's own Python syntax highlighter, because that's Semshi's job. If you turn it off, Vim may add incorrect highlights. |
| `g:semshi#simplify_markup` | `v:true` | Simplify Python markup. Semshi introduces lots of new colors, so this option makes the highlighting of other syntax elements less distracting, binding most of them to `pythonStatement`. If you think Semshi messes with your colorscheme too much, try turning this off. |
| `g:semshi#error_sign` | `v:true` | Show a sign in the sign column if a syntax error occurred. |
| `g:semshi#error_sign_delay` | `1.5` | Delay in seconds until the syntax error sign is displayed. (A low delay time may distract while typing.) |
| `g:semshi#always_update_all_highlights` | `v:false` | Update all visible highlights for every change. (Semshi tries to detect small changes and update only changed highlights. This can lead to some missing highlights. Turn this on for more reliable highlighting, but a small additional overhead.) |
| `g:semshi#tolerate_syntax_errors` | `v:true` | Tolerate some minor syntax errors to update highlights even when the syntax is (temporarily) incorrect. (Smoother experience, but comes with some overhead.) |
| `g:semshi#update_delay_factor` | `0.0` | Factor to delay updating of highlights. Updates will be delayed by `factor * number of lines` seconds. This is useful if instant re-parsing while editing large files stresses your CPU too much. A good starting point may be a factor of `0.0001` (that is, in a file with 1000 lines, parsing will be delayed by 0.1 seconds). |
| `g:semshi#self_to_attribute` | `v:true` | Prefer the attribute of `self`/`cls` nodes. That is, when selecting the `self` in `self.foo`, Semshi will use the instance attribute `foo` instead. |

### Highlights

Semshi sets these highlights/signs (which work best on dark backgrounds):

```VimL
hi semshiLocal           ctermfg=209 guifg=#ff875f
hi semshiGlobal          ctermfg=214 guifg=#ffaf00
hi semshiImported        ctermfg=214 guifg=#ffaf00 cterm=bold gui=bold
hi semshiParameter       ctermfg=75  guifg=#5fafff
hi semshiParameterUnused ctermfg=117 guifg=#87d7ff cterm=underline gui=underline
hi semshiFree            ctermfg=218 guifg=#ffafd7
hi semshiBuiltin         ctermfg=207 guifg=#ff5fff
hi semshiAttribute       ctermfg=49  guifg=#00ffaf
hi semshiSelf            ctermfg=249 guifg=#b2b2b2
hi semshiUnresolved      ctermfg=226 guifg=#ffff00 cterm=underline gui=underline
hi semshiSelected        ctermfg=231 guifg=#ffffff ctermbg=161 guibg=#d7005f

hi semshiErrorSign       ctermfg=231 guifg=#ffffff ctermbg=160 guibg=#d70000
hi semshiErrorChar       ctermfg=231 guifg=#ffffff ctermbg=160 guibg=#d70000
sign define semshiError text=E> texthl=semshiErrorSign
```
If you want to overwrite them in your vimrc, make sure to apply them *after* Semshi has set the defaults, e.g. in a function:

```VimL
function MyCustomHighlights()
    hi semshiGlobal      ctermfg=red guifg=#ff0000
endfunction
autocmd FileType python call MyCustomHighlights()
```

Also, if you want the highlight groups to persist across colorscheme switches, add:

```VimL
autocmd ColorScheme * call MyCustomHighlights()
```

## Usage

Semshi parses and highlights code in all files with a `.py` extension. With every change to the buffer, the code is re-parsed and highlights are updated. When moving the cursor above a name, all nodes with the same name in the same scope are additionally marked. Semshi also attempts to tolerate syntax errors as you type.


### Commands

The following commands can be executed via `:Semshi <command>`:

| Command | Description |
| --- | --- |
| `enable` | Enable highlighting for current buffer. |
| `disable` | Disable highlighting for current buffer. |
| `toggle` | Toggle highlighting for current buffer. |
| `pause` | Like `disable`, but doesn't clear the highlights. |
| `highlight` | Force update of highlights for current buffer. (Useful when for some reason highlighting hasn't been triggered.)  |
| `clear` | Clear all highlights in current buffer. |
| `rename [new_name]` | Rename node under the cursor. If `new_name` isn't set, you're interactively prompted for the new name. |
| `error` | Echo current syntax error message. |
| `goto error` | Jump to current syntax error. |
| `goto (name\|function\|class) (next\|prev\|first\|last)` | Jump to next/previous/first/last name/function/class. (See below for sample mappings.) |
| `goto [highlight_group] (next\|prev\|first\|last)` | Jump to next/previous/first/last node with given highlight group. (Groups: `local`, `unresolved`, `attribute`, `builtin`, `free`, `global`, `parameter`, `parameterUnused`, `self`, `imported`)  |

Here are some possible mappings:

```VimL
nmap <silent> <leader>rr :Semshi rename<CR>

nmap <silent> <Tab> :Semshi goto name next<CR>
nmap <silent> <S-Tab> :Semshi goto name prev<CR>

nmap <silent> <leader>c :Semshi goto class next<CR>
nmap <silent> <leader>C :Semshi goto class prev<CR>

nmap <silent> <leader>f :Semshi goto function next<CR>
nmap <silent> <leader>F :Semshi goto function prev<CR>

nmap <silent> <leader>gu :Semshi goto unresolved first<CR>
nmap <silent> <leader>gp :Semshi goto parameterUnused first<CR>

nmap <silent> <leader>ee :Semshi error<CR>
nmap <silent> <leader>ge :Semshi goto error<CR>
```

## Limitations

- Features like wildcard imports (`from foo import *`) or fancy metaprogramming may hide name bindings from simple static analysis. In that case, Semshi can't pick them up and may show these names as unresolved or highlight incorrectly.

- While a syntax error is present (which can't be automatically compensated), Semshi can't update any highlights. So, highlights may be temporarily incorrect or misplaced while typing.

- Although Semshi parses the code asynchronously and is not *that* slow, editing large files may stress your CPU and cause highlighting delays.

- Semshi works with the same syntax version as your Neovim Python 3 provider. This means you can't use Semshi on code that's Python 2-only or uses incompatible syntax features. (Support for different versions is planned. See [#19](https://github.com/numirias/semshi/issues/19))


## FAQ

### How does Semshi compare to refactoring/completion plugins like [jedi-vim](https://github.com/davidhalter/jedi-vim)?

Semshi's primary focus is to provide reasonably fast semantic highlighting to make code easier to read. It's meant to replace your syntax highlighter, not your refactoring tools. So, Semshi works great alongside refactoring and completion libraries like Jedi.

### Is Vim 8 supported?

No. Semshi relies on Neovim's fast highlighting API to quickly update lots of highlights. Regular Vim unfortunately doesn't have an equivalent API. (If you think this can be implemented for Vim 8, let me know.)

### Is Python 2 supported?

No. [Migrate your code already!](https://pythonclock.org/) (Support for Python < 3.5 *may* be coming, but don't expect it too soon. See [#19](https://github.com/numirias/semshi/issues/19))

### Semshi is too slow.

Semshi should be snappy on reasonably-sized Python files with ordinary hardware. But some plugins hooking the same events (e.g. [deoplete.nvim](https://github.com/Shougo/deoplete.nvim)) may cause significant delays. If you experience any performance problems, please file an issue.

### Semshi is slow together with [deoplete.nvim](https://github.com/Shougo/deoplete.nvim).

Completion triggers may block Semshi from highlighting instantly. Try to increase Deoplete's `auto_complete_delay`, e.g.:

```VimL
call deoplete#custom#option('auto_complete_delay', 100)
```

Or in older (<=5.2) Deoplete versions:

```VimL
let g:deoplete#auto_complete_delay = 100
```

### There are some incorrect extra highlights.

You might be using other Python syntax highlighters alongside (such as [python-syntax](https://github.com/vim-python/python-syntax)) which may interfere with Semshi. Try to disable these plugins if they cause problems.

### Sometimes highlights aren't updated.

As you type code, you introduce temporary syntax errors, e.g. when opening a new bracket. Not all syntax errors can be compensated, so most of the time Semshi can only refresh highlights when the syntax becomes correct again.

## Contributing

I absolutely need your help with testing and improving Semshi. If you found a bug or have a suggestion, please don't hesitate to [file an issue](https://github.com/numirias/semshi/issues/new).
