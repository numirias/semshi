# Semshi

[![Build Status](https://travis-ci.org/numirias/semshi.svg?branch=master)](https://travis-ci.org/numirias/semshi)
[![codecov](https://codecov.io/gh/numirias/semshi/branch/master/graph/badge.svg)](https://codecov.io/gh/numirias/semshi)
![Python Versions](https://img.shields.io/badge/python-3.5,%203.6-blue.svg)

Semshi provides semantic syntax highlighting for Python in Neovim.

(Work in progress)

## Installation

- You need Neovim with Python 3 support (`:echo has("python3")`). To install the Python provider run:

      pip3 install neovim --upgrade 
    
- Add `numirias/semshi` via your plugin manager. If you're using [vim-plug](https://github.com/junegunn/vim-plug), add... 

      Plug 'numirias/semshi', {'do': ':UpdateRemotePlugins'}
      
  ...and run `:PlugInstall`.

- You may also need to run `:UpdateRemotePlugins` to update the plugin manifest.

- (If you insist on manual installation, download the source and place it in a directory in your Vim runtime path.)
