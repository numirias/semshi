from functools import wraps

import neovim

from .handler import BufferHandler
from .node import groups


def if_active(func):
    """Decorator to execute `func` only if the plugin is active."""
    @wraps(func)
    def wrapper(self):
        if not self._options.active: # pylint: disable=protected-access
            return
        func(self)
    return wrapper

_subcommands = {}

def subcommand(func):
    _subcommands[func.__name__] = func
    return func


@neovim.plugin
class Plugin:
    """Semshi Neovim plugin.

    The plugin handles vim events and commands, and delegates them to a buffer
    handler. (Each buffer is handled by a semshi.BufferHandler instance.)
    """
    # File pattern when to attach event handlers
    _pattern = '*.py'

    def __init__(self, vim):
        self._vim = vim
        self._active = None
        self._handlers = {}
        self._cur_handler = None
        self._options = None

    # Must not be async because we have to make sure that switching the buffer
    # handler is completed before other events are handled.
    @neovim.autocmd('BufEnter', pattern=_pattern, sync=True)
    def event_buf_enter(self):
        if self._options is None:
            # We'd want to do initialization on VimEnter, but that event may be
            # called *after* BufEnter, so we need to trigger it here.
            self._options = Options(self._vim)
        if not self._options.active:
            return
        self._switch_handler()
        self._update_viewport()
        if self._cur_handler.enabled:
            self._cur_handler.update()

    @neovim.autocmd('VimResized', pattern=_pattern, sync=False)
    @if_active
    def event_vim_resized(self):
        self._update_viewport()
        if self._cur_handler.enabled:
            self._mark_selected()

    @neovim.autocmd('CursorMoved', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved(self):
        self._update_viewport()
        if self._cur_handler.enabled:
            self._mark_selected()

    @neovim.autocmd('CursorMovedI', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved_insert(self):
        self._update_viewport()
        if self._cur_handler.enabled:
            self._mark_selected()

    @neovim.autocmd('TextChanged', pattern=_pattern, sync=False)
    @if_active
    def event_text_changed(self):
        if self._cur_handler.enabled:
            self._cur_handler.update()

    @neovim.autocmd('TextChangedI', pattern=_pattern, sync=False)
    @if_active
    def event_text_changed_insert(self):
        if self._cur_handler.enabled:
            self._cur_handler.update()

    @neovim.autocmd('VimLeave', pattern=_pattern, sync=True)
    @if_active
    def event_vim_leave(self):
        self._cur_handler.shutdown()

    @neovim.command('Semshi', nargs='*', complete='customlist,SemshiComplete',
                    sync=True)
    def cmd_semshi(self, args):
        if not args:
            self._vim.out_write('This is semshi.\n')
            return
        try:
            func = _subcommands[args[0]]
        except KeyError:
            self._vim.err_write('Subcommand not found: %s\n' % args[0])
            return
        func(self, *args[1:])

    @staticmethod
    @neovim.function('SemshiComplete', sync=True)
    def func_complete(arg):
        lead, *_ = arg
        return [c for c in _subcommands if c.startswith(lead)]

    @subcommand
    def version(self):
        self._vim.out_write('semshi v0.0\n')

    @subcommand
    def enable(self):
        self._cur_handler.enabled = True
        self.highlight()

    @subcommand
    def disable(self):
        self._cur_handler.enabled = False
        self.clear()

    @subcommand
    def highlight(self):
        self._cur_handler.update(force=True, sync=True)

    @subcommand
    def clear(self):
        self._cur_handler.clear_highlights()

    @subcommand
    def rename(self, new_name=None):
        self._cur_handler.rename(self._vim.current.window.cursor, new_name)

    @subcommand
    def goto(self, *args, **kwargs):
        self._cur_handler.goto(*args, **kwargs)

    @subcommand
    def error(self):
        self._cur_handler.show_error()

    def _switch_handler(self):
        buf = self._vim.current.buffer
        try:
            handler = self._handlers[buf]
        except KeyError:
            handler = BufferHandler(buf, self._vim, self._options)
            self._handlers[buf] = handler
        self._cur_handler = handler

    def _update_viewport(self):
        start = self._vim.eval('line("w0")')
        stop = self._vim.eval('line("w$")')
        self._cur_handler.viewport(start, stop)

    def _mark_selected(self):
        if not self._options.mark_selected_nodes:
            return
        self._cur_handler.mark_selected(self._vim.current.window.cursor)


class Options:
    """Plugin options.

    The options will only be read and set once on init.
    """
    _defaults = {
        'active': True,
        'excluded_buffers': [],
        'excluded_hl_groups': ['local'],
        'mark_selected_nodes': True,
        'no_default_builtin_highlight': True,
        'simplify_markup': True,
        'error_sign': True,
        'error_sign_delay': 1.5,
        'always_update_all_highlights': False,
        'tolerate_syntax_errors': True,
        'update_delay_factor': .0,
        'self_to_attribute': True,
    }

    def __init__(self, vim):
        for key, val_default in Options._defaults.items():
            val = vim.vars.get('semshi#' + key, val_default)
            # vim.vars doesn't support setdefault(), so set value manually
            vim.vars['semshi#' + key] = val
            try:
                converter = getattr(Options, '_convert_' + key)
            except AttributeError:
                pass
            else:
                val = converter(val)
            setattr(self, key, val)

    @staticmethod
    def _convert_excluded_hl_groups(items):
        try:
            return [groups[g] for g in items]
        except KeyError as e:
            raise Exception('"%s" is an unknown highlight group.' % e.args[0])
