from functools import partial, wraps
import threading

import neovim

from .handler import BufferHandler
from .node import groups
from .util import debug_time


def if_active(func):
    """Decorator to execute `func` only if the plugin is active."""
    @wraps(func)
    def wrapper(self):
        if not self._options.active: # pylint: disable=protected-access
            return
        func(self)
    return wrapper


@neovim.plugin
class Plugin:
    """Semshi neovim plugin."""

    # File pattern when to attach event handlers
    _pattern = '*.py'

    def __init__(self, vim):
        self.vim = vim
        self._options = Options(vim)
        self._active = None
        self._handlers = {}
        self._cur_handler = None

    # Must not be async because we have to make sure that switching the buffer
    # handler is completed before other events are handled.
    @neovim.autocmd('BufEnter', pattern=_pattern, sync=True)
    @if_active
    def event_buf_enter(self):
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

    @neovim.command('Semshi', nargs='*', sync=True)
    def cmd_semshi(self, args):
        if not args:
            self.vim.out_write('This is semshi.\n')
            return
        try:
            func = getattr(self, 'cmd_%s' % args[0])
        except AttributeError:
            self.vim.err_write('Sub command not found: %s\n' % args[0])
            return
        func(*args[1:])

    def cmd_version(self):
        self.vim.out_write('semshi v0.0\n')

    def cmd_highlight(self):
        self._cur_handler.update(force=True, sync=True)

    def _switch_handler(self):
        buf = self.vim.current.buffer
        try:
            handler = self._handlers[buf]
        except KeyError:
            handler = BufferHandler(
                partial(self._add_highlights, buf),
                partial(self._clear_highlights, buf),
                partial(self._code, buf),
                self._cursor,
                self._options.excluded_hl_groups,
                self._options.mark_original_node,
            )
            self._handlers[buf] = handler
        self._cur_handler = handler

    def _update_viewport(self):
        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        self._cur_handler.viewport(start, stop)

    def _mark_selected(self):
        self._cur_handler.mark_selected(self.vim.current.window.cursor)

    def _cursor(self, sync):
        func = lambda: self.vim.current.window.cursor
        return func() if sync else self._wait_for(func)

    def _code(self, buf, sync):
        func = lambda: '\n'.join(buf[:])
        return func() if sync else self._wait_for(func)

    def _wait_for(self, func):
        """Run `func` in async context, block until done and return result.

        Needed when an async event handler needs the result of an API call.
        """
        event = threading.Event()
        res = None
        def wrapper():
            nonlocal res
            res = func()
            event.set()
        self.vim.async_call(wrapper)
        event.wait()
        return res

    @debug_time(None, lambda _, __, nodes: '%d nodes' % len(nodes))
    def _add_highlights(self, buf, node_or_nodes):
        if not node_or_nodes:
            return
        if not isinstance(node_or_nodes, list):
            buf.add_highlight(*node_or_nodes)
            return
        self._call_atomic_async(
            [('nvim_buf_add_highlight', (buf, *n)) for n in node_or_nodes])

    @debug_time(None, lambda _, __, nodes: '%d nodes' % len(nodes))
    def _clear_highlights(self, buf, node_or_nodes):
        if not node_or_nodes:
            return
        if not isinstance(node_or_nodes, list):
            buf.clear_highlight(*node_or_nodes)
            return
        # Don't specify line range to clear explicitly because we can't
        # reliably determine the correct range
        self._call_atomic_async(
            [('nvim_buf_clear_highlight', (buf, *n)) for n in node_or_nodes])

    def _call_atomic_async(self, calls):
        # Need to update in small batches to avoid
        # https://github.com/neovim/python-client/issues/310
        batch_size = 3000
        for i in range(0, len(calls), batch_size):
            self.vim.api.call_atomic(calls[i:i + batch_size], async=True)


class Options:
    """Plugin options.

    Options are fetched lazily and only evaluated once.
    """
    def __init__(self, vim):
        self._vim = vim

    def __getattr__(self, item):
        val = self.__getattribute__('_option_%s' % item)()
        setattr(self, item, val)
        return val

    def _option(self, option_name):
        return self._vim.eval('g:semshi#%s' % option_name)

    def _option_active(self):
        return bool(self._option('active'))

    def _option_excluded_hl_groups(self):
        try:
            return [groups[g] for g in self._option('excluded_hl_groups')]
        except KeyError as e:
            raise Exception('"%s" is an unknown highlight group.' % e.args[0])

    def _option_mark_original_node(self):
        return bool(self._option('mark_original_node'))
