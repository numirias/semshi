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
    """Semshi neovim plugin."""

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
            # We'd want to initialize the options on VimEnter, but that event
            # is called *after* BufEnter, so we need to do it here.
            self._options = Options(self._vim)
        if not self._options.active:
            return
        self._switch_handler()
        self._update_viewport()
        self._cur_handler.update()

    @neovim.autocmd('VimResized', pattern=_pattern, sync=False)
    @if_active
    def event_vim_resized(self):
        self._update_viewport()
        self._mark_selected()

    @neovim.autocmd('CursorMoved', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved(self):
        self._update_viewport()
        self._mark_selected()

    @neovim.autocmd('CursorMovedI', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved_insert(self):
        self._update_viewport()
        self._mark_selected()

    @neovim.autocmd('TextChanged', pattern=_pattern, sync=False)
    @if_active
    def event_text_changed(self):
        self._cur_handler.update()

    @neovim.autocmd('TextChangedI', pattern=_pattern, sync=False)
    @if_active
    def event_text_changed_insert(self):
        self._cur_handler.update()

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
    def highlight(self):
        self._cur_handler.update(force=True, sync=True)

    @subcommand
    def rename(self, new_name=None):
        self._cur_handler.rename(self._vim.current.window.cursor, new_name)

    @subcommand
    def goto(self, *args, **kwargs):
        self._cur_handler.goto(*args, **kwargs)

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

    """
    def __init__(self, vim):
        self._vim = vim
        for name, func in Options.__dict__.items():
            if not name.startswith('_option_'):
                continue
            setattr(self, name[8:], func(self))

    def _option(self, option_name):
        return self._vim.eval('g:semshi#%s' % option_name)

    def _option_active(self):
        return bool(self._option('active'))

    def _option_excluded_hl_groups(self):
        try:
            return [groups[g] for g in self._option('excluded_hl_groups')]
        except KeyError as e:
            raise Exception('"%s" is an unknown highlight group.' % e.args[0])

    def _option_mark_selected_nodes(self):
        return self._option('mark_selected_nodes')

    def _option_error_sign(self):
        return bool(self._option('error_sign'))

    def _option_error_sign_delay(self):
        return self._option('error_sign_delay')

    def _option_always_update_all_highlights(self):
        return bool(self._option('always_update_all_highlights'))

    def _option_tolerate_syntax_errors(self):
        return bool(self._option('tolerate_syntax_errors'))

    def _option_update_delay_factor(self):
        return self._option('update_delay_factor')

    def _option_self_to_attribute(self):
        return bool(self._option('self_to_attribute'))
