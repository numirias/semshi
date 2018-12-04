from functools import wraps

try:
    import pynvim as neovim
except ImportError:
    import neovim

from .handler import BufferHandler
from .node import groups


def if_active(func):
    """Decorator to execute `func` only if the plugin is active.

    Initializes the plugin if it's uninitialized.
    """
    @wraps(func)
    def wrapper(self):
        # pylint: disable=protected-access
        if self._options is None:
            self._init_with_vim()
        if not self._options.active:
            return
        func(self)
    return wrapper

_subcommands = {}

def subcommand(func):
    """Register `func` as a ":Semshi [...]" subcommand."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # pylint: disable=protected-access
        if self._cur_handler is None:
            self.echo_error('Semshi doesn\'t currently handle this file. '
                            '(match pattern: "%s")' % Plugin._pattern)
            return
        func(self, *args, **kwargs)
    _subcommands[func.__name__] = wrapper
    return wrapper


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

    def _init_with_vim(self):
        """Initialize with vim available.

        Initialization code which interacts with vim can't be safely put in
        __init__ because vim itself may not be fully started up.
        """
        self._options = Options(self._vim)
        if not self._options.active:
            return
        self._switch_handler()
        self._update_viewport()

    def echo(self, *msgs):
        msg = ' '.join([str(m) for m in msgs])
        self._vim.out_write(msg + '\n')

    def echo_error(self, *msgs):
        msg = ' '.join([str(m) for m in msgs])
        self._vim.err_write(msg + '\n')

    # Must not be async because we have to make sure that switching the buffer
    # handler is completed before other events are handled.
    @neovim.autocmd('BufEnter', pattern=_pattern, sync=True)
    @if_active
    def event_buf_enter(self):
        self._switch_handler()
        if self._cur_handler.enabled:
            self._update_viewport()
            self._cur_handler.update()

    @neovim.autocmd('VimResized', pattern=_pattern, sync=False)
    @if_active
    def event_vim_resized(self):
        if self._cur_handler.enabled:
            self._update_viewport()
            self._mark_selected()

    @neovim.autocmd('CursorMoved', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved(self):
        if self._cur_handler.enabled:
            self._update_viewport()
            self._mark_selected()

    @neovim.autocmd('CursorMovedI', pattern=_pattern, sync=False)
    @if_active
    def event_cursor_moved_insert(self):
        if self._cur_handler.enabled:
            self._update_viewport()
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
            self.echo('This is semshi.')
            return
        try:
            func = _subcommands[args[0]]
        except KeyError:
            self.echo_error('Subcommand not found: %s' % args[0])
            return
        func(self, *args[1:])

    @staticmethod
    @neovim.function('SemshiComplete', sync=True)
    def func_complete(arg):
        lead, *_ = arg
        return [c for c in _subcommands if c.startswith(lead)]

    @subcommand
    def enable(self):
        self._update_viewport()
        self._cur_handler.enabled = True
        self.highlight()

    @subcommand
    def disable(self):
        self._cur_handler.enabled = False
        self.clear()

    @subcommand
    def toggle(self):
        if self._cur_handler.enabled:
            self.disable()
        else:
            self.enable()

    @subcommand
    def pause(self):
        self._cur_handler.enabled = False

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
        'mark_selected_nodes': 1,
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
