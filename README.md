# Semshi

[![Build Status](https://travis-ci.org/numirias/semshi.svg?branch=master)](https://travis-ci.org/numirias/semshi)
[![codecov](https://codecov.io/gh/numirias/semshi/branch/master/graph/badge.svg)](https://codecov.io/gh/numirias/semshi)
![Python Versions](https://img.shields.io/badge/python-3.5,%203.6-blue.svg)

Semshi provides semantic highlighting for Python in Neovim.

Most syntax highlighters are regex-based and unaware of semantics. Semshi performs static analysis of Python code as you type. It asynchronously builds a syntax tree and symbol table to understand the scopes of locals, globals, arguments etc. and highlight them differently. This makes code easier to read and lets you quickly detect missing imports, unused arguments or misspelled names.

| With Semshi | Without Semshi |
| --- | --- |
| ![After](https://i.imgur.com/QUnGdU8.png) | ![Before](https://i.imgur.com/eiD1Miz.png) |

In above example, you can easily distinguish arguments (blue), globals (orange), instance attributes (teal), etc., and the unresolved names (yellow underlined) are obvious. Also, Semshi detects that first `list` is assigned locally, while the default highlighter still shows it as builtin.

## Features

- Different highlighting of locals, globals, imports, function parameters, builtins, attributes, arguments, free and unresolved names.
- Highlighting of all currently selected nodes.
- Indication of syntax errors.
- Highlighting of unused arguments.

**TODO:**
- Refactoring tools.

## Installation

- You need Neovim with Python 3 support (`:echo has("python3")`). To install the Python provider run:

      pip3 install neovim --upgrade 
    
- Add `numirias/semshi` via your plugin manager. If you're using [vim-plug](https://github.com/junegunn/vim-plug), add... 

      Plug 'numirias/semshi', {'do': ':UpdateRemotePlugins'}
      
  ...and run `:PlugInstall`.

- You may also need to run `:UpdateRemotePlugins` to update the plugin manifest.

- (If you insist on manual installation, download the source and place it in a directory in your Vim runtime path.)


## Configuration

### Options

You can set these options in your vimrc (`~/.config/nvim/init.vim`):

| Option | Default | Description |
| --- | --- | --- |
| `g:semshi#active` | `1` | Activate event handlers. |
| `g:semshi#excluded_hl_groups` | `['local']` | List of highlight groups to not highlight. Chose from `local`, `unresolved`, `attribute`, `builtin`, `free`, `global`, `parameter`, `parameterUnused`, `self`, `imported`. (It's recommended to keep `local` in the list because highlighting all locals in a large file can cause performance issues.) |
| `g:semshi#mark_selected_nodes ` | ` 1` | Mark selected nodes (those with the same name and scope as the one under the cursor). Set to `2` to highlight the node currently under the cursor, too. |
| `g:semshi#no_default_builtin_highlight` | `1` | Disable builtin highlighting by Vim's own Python syntax highlighter, because that's Semshi's job. If you turn it off, Vim will add incorrect highlights. |
| `g:semshi#simplify_markup` | `1` | Simplify Python markup. Semshi introduces lots of new colors, so this option makes the highlighting of other syntax elements less distracting, binding most of them to `pythonStatement`. If you think Semshi messes with your colorscheme too much, try turning this off. |
| `g:semshi#error_sign` | `1` | Show a sign in the sign column if a syntax error occurred. |
| `g:semshi#error_sign_delay` | `1.5` | Delay in seconds until the syntax error sign is displayed. (A low delay time may distract while typing.) |
| `g:semshi#always_update_all_highlights` | `0` | Update all visible highlights for every change. (Semshi tries to detect small changes and update only changed highlights. This can lead to some missing highlights. Turn this on for more reliable highlighting, but a small additional overhead.) |

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

Once installed, Semshi automatically parses and highlights code in any open file with a `.py` extension. With every change to the buffer, the code is re-parsed and highlights are updated. When moving the cursor above a name, all nodes with the same name in the same scope are highlighted, too. Semshi also attempts to compensate syntax errors as you type.

But bear in mind that static analysis is limited. For example, wildcard imports (`from foo import *`) and `eval` or `exec` calls can hide names which Semshi won't pick up or show as unresolved. Also, whenever a syntax error is present (which can't be automatically compensated), highlights can't be updated.


### Commands

The following commands can be executed via `:Semshi <command>`:

| Command | Description |
| --- | --- |
| `version` | Show version. |
| `highlight` | Force update of highlights for current buffer. (Useful when for some reason highlighting hasn't been triggered.)  |


## FAQ

### Is Vim 8 supported?

No. Semshi relies on Neovim's fast highlighting API to update highlights quickly for which there is currently no equivalent in regular Vim. If you think this can be implemented for Vim 8, let me know.

### Is Python 2 supported?

No. Currently, support for Python < 3.5 isn't planned. Migrate your code already!

### There are some annoying extra highlights.

You might be using other Python syntax highlighters alongside (such as [python-syntax](https://github.com/vim-python/python-syntax)) which may interfere with Semshi. Try to disable these plugins if they cause problems.

### Sometimes highlights aren't updated.

As you type code, you introduce temporary syntax errors, e.g. when opening a new bracket. Not all syntax errors can be compensated, so most of the time Semshi can only refresh highlights when the syntax becomes correct again.

## Contributing

I absolutely need your help with testing and improving Semshi. If you found a bug or have a suggestion, please don't hesitate to [file an issue](https://github.com/numirias/semshi/issues/new).
