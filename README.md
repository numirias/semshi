# Semshi

[![Build Status](https://travis-ci.org/numirias/semshi.svg?branch=master)](https://travis-ci.org/numirias/semshi)
[![codecov](https://codecov.io/gh/numirias/semshi/branch/master/graph/badge.svg)](https://codecov.io/gh/numirias/semshi)
![Python Versions](https://img.shields.io/badge/python-3.5,%203.6-blue.svg)

Semshi provides semantic highlighting for Python in Neovim.

As opposed to regex-based syntax highlighters, Semshi performs actual static analysis of Python code as you type. It builds a syntax tree and symbol tables to highlight names based on their scope and context. This makes code easier to read and lets you quickly identify missing imports, unused arguments, misspelled names and more.

| With Semshi | Without Semshi |
| --- | --- |
| ![After](https://i.imgur.com/rDBSM8s.png) | ![Before](https://i.imgur.com/t40TNZ6.png) |

In above example, you can easily distinguish arguments (blue), instance attributes (teal), globals (orange), unresolved globals (yellow underlined), etc. Also, Semshi understands that the first `list` is assigned locally, while the default highlighter still shows it as builtin.

## Features

- Different highlighting of locals, globals, imports, used and unused function parameters, builtins, attributes, free and unresolved names.

- Scope-aware marking and renaming of related nodes.

  ![Renaming](https://i.imgur.com/5zWRFyg.gif)

- Indication of syntax errors.

  ![Syntax errors](https://i.imgur.com/tCj9myJ.gif)

## Installation

- You need Neovim with Python 3 support (`:echo has("python3")`). To install the Python provider run:

      pip3 install neovim --upgrade 
    
- Add `numirias/semshi` via your plugin manager. If you're using [vim-plug](https://github.com/junegunn/vim-plug), add... 

      Plug 'numirias/semshi', {'do': ':UpdateRemotePlugins'}
      
  ...and run `:PlugInstall`.

- You may also need to run `:UpdateRemotePlugins` manually to update the plugin manifest.

- (If you insist on manual installation, download the source and place it in a directory in your Vim runtime path.)


## Configuration

### Options

You can set these options in your vimrc (`~/.config/nvim/init.vim`):

| Option | Default | Description |
| --- | --- | --- |
| `g:semshi#active` | `1` | Activate event handlers. |
| `g:semshi#excluded_hl_groups` | `['local']` | List of highlight groups to not highlight. Chose from `local`, `unresolved`, `attribute`, `builtin`, `free`, `global`, `parameter`, `parameterUnused`, `self`, `imported`. (It's recommended to keep `local` in the list because highlighting all locals in a large file can cause performance issues.) |
| `g:semshi#mark_selected_nodes ` | ` 1` | Mark selected nodes (those with the same name and scope as the one under the cursor). Set to `2` to highlight the node currently under the cursor, too. |
| `g:semshi#no_default_builtin_highlight` | `1` | Disable builtin highlighting by Vim's own Python syntax highlighter, because that's Semshi's job. If you turn it off, Vim may add incorrect highlights. |
| `g:semshi#simplify_markup` | `1` | Simplify Python markup. Semshi introduces lots of new colors, so this option makes the highlighting of other syntax elements less distracting, binding most of them to `pythonStatement`. If you think Semshi messes with your colorscheme too much, try turning this off. |
| `g:semshi#error_sign` | `1` | Show a sign in the sign column if a syntax error occurred. |
| `g:semshi#error_sign_delay` | `1.5` | Delay in seconds until the syntax error sign is displayed. (A low delay time may distract while typing.) |
| `g:semshi#always_update_all_highlights` | `0` | Update all visible highlights for every change. (Semshi tries to detect small changes and update only changed highlights. This can lead to some missing highlights. Turn this on for more reliable highlighting, but a small additional overhead.) |
| `g:semshi#tolerate_syntax_errors` | `1` | Tolerate some minor syntax errors to update highlights even when the syntax is (temporarily) incorrect. (Smoother experience, but comes with some overhead.) |

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
sign define semshiError text=E> texthl=semshiErrorSign
```
If you want to overwrite them in your vimrc, make sure to apply them *after* Semshi has set the defaults, e.g. in a function:

```VimL
function MyCustomHighlights()
    hi semshiGlobal      ctermfg=red guifg=#ff0000
endfunction
autocmd FileType python call MyCustomHighlights()
```

## Usage

Semshi parses and highlights code in all files with a `.py` extension. With every change to the buffer, the code is re-parsed and highlights are updated. When moving the cursor above a name, all nodes with the same name in the same scope are additionally marked. Semshi also attempts to tolerate syntax errors as you type.


### Commands

The following commands can be executed via `:Semshi <command>`:

| Command | Description |
| --- | --- |
| `version` | Show version. |
| `highlight` | Force update of highlights for current buffer. (Useful when for some reason highlighting hasn't been triggered.)  |
| `rename [new_name]` | Rename node under the cursor. If `new_name` isn't set, you're interactively prompted for the new name. |
| `goto ("name"\|"function"\|"class") ("next"\|"prev")` | Jump to next/previous name/function/class. (See below for sample mappings.) |

Here are some possible mappings:

```VimL
nmap <silent> <leader>rr :Semshi rename<CR>

nmap <silent> <Tab> :Semshi goto name next<CR>
nmap <silent> <S-Tab> :Semshi goto name prev<CR>

nmap <silent> <leader>c :Semshi goto class next<CR>
nmap <silent> <leader>C :Semshi goto class prev<CR>

nmap <silent> <leader>f :Semshi goto function next<CR>
nmap <silent> <leader>F :Semshi goto function prev<CR>
```

## Limitations

- Some features such as wildcard imports (`from foo import *`) and fancy metaprogramming may hide names which Semshi won't pick up and may show as unresolved or highlight incorrectly.

- Whenever a syntax error is present (which can't be automatically compensated), highlights can't be updated. So you may experience that highlights are temporarily incorrect while typing.

- Although Semshi does its work asynchronously and is not *that* slow, editing large files may stress your CPU and cause delayed highlighting.


## FAQ

### Is Vim 8 supported?

No. Semshi relies on Neovim's fast highlighting API to update highlights quickly for which there is currently no equivalent in regular Vim. If you think this can be implemented for Vim 8, let me know.

### Is Python 2 supported?

No. Currently, support for Python < 3.5 isn't planned. Migrate your code already!

### There are some incorrect extra highlights.

You might be using other Python syntax highlighters alongside (such as [python-syntax](https://github.com/vim-python/python-syntax)) which may interfere with Semshi. Try to disable these plugins if they cause problems.

### Sometimes highlights aren't updated.

As you type code, you introduce temporary syntax errors, e.g. when opening a new bracket. Not all syntax errors can be compensated, so most of the time Semshi can only refresh highlights when the syntax becomes correct again.

## Contributing

I absolutely need your help with testing and improving Semshi. If you found a bug, have a suggestion, or just want to give usage feedback, please don't hesitate to [file an issue](https://github.com/numirias/semshi/issues/new).
