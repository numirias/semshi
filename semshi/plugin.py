import neovim

from .handler import BufferHandler
from .node import groups
from .util import logger


pattern = '*.py'


def if_active(func):
    def wrapper(self):
        if not self.options.active:
            return
        func(self)
    return wrapper


class Options:

    def __init__(self, vim):
        self._vim = vim

    def __getattr__(self, item):
        logger.debug('not found %s', item)
        val = self.__getattribute__('_option_%s' % item)()
        setattr(self, item, val)
        return val

    def _option(self, option_name):
        return self._vim.eval('g:semshi#%s' % option_name)

    def _option_active(self):
        return bool(self._option('active'))

    def _option_excluded_hl_groups(self):
        return [groups[g] for g in self._option('excluded_hl_groups')]

    def _option_mark_original_node(self):
        return bool(self._option('mark_original_node'))


@neovim.plugin
class Plugin:

    def __init__(self, vim):
        self.vim = vim
        self.options = Options(vim)
        self._active = None
        self._handlers = {}
        self._current_handler = None

    # Needs to be sync=True because we have to make sure that switching the
    # buffer handler is completed before other events are handled.
    @neovim.autocmd('BufEnter', pattern=pattern, sync=True)
    @if_active
    def event_buf_enter(self):
        self.switch_handler()
        # TODO set these elsewehere and just once
        self.update_viewport()
        self._current_handler.update()

    @neovim.autocmd('VimResized', pattern=pattern, sync=False)
    @if_active
    def event_vim_resized(self):
        self.visible_area_changed()

    @neovim.autocmd('TextChanged', pattern=pattern, sync=False)
    @if_active
    def event_text_changed(self):
        self._current_handler.update()

    @neovim.autocmd('TextChangedI', pattern=pattern, sync=False)
    @if_active
    def event_text_changed_insert(self):
        self._current_handler.update()

    @neovim.autocmd('CursorMoved', pattern=pattern, sync=False)
    @if_active
    def event_cursor_moved(self):
        self.visible_area_changed()
        self._current_handler.mark_selected(self.vim.current.window.cursor)

    @neovim.autocmd('CursorMovedI', pattern=pattern, sync=False)
    @if_active
    def event_cursor_moved_insert(self):
        self.visible_area_changed()
        self._current_handler.mark_selected(self.vim.current.window.cursor)

    @neovim.command('Semshi', range='', nargs='*', sync=True)
    def cmd_semshi(self, args, range):
        self.vim.out_write('This is semshi. %s %s\n' % (args, range))

    def visible_area_changed(self):
        self.update_viewport()
        self._current_handler.add_visible_highlights()

    def switch_handler(self):
        buf = self.vim.current.buffer
        try:
            handler = self._handlers[buf]
        except KeyError:
            handler = BufferHandler(self, buf)
            self._handlers[buf] = handler
        self._current_handler = handler

    def update_viewport(self):
        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        logger.debug('visible %d - %d', start, stop)
        self._current_handler.set_viewport(start, stop)

    def add_highlights(self, nodes, buf):
        logger.debug('adding %d highlights', len(nodes))
        if not nodes:
            return
        calls = [('nvim_buf_add_highlight', (buf, *n)) for n in nodes]
        self.call_atomic_async(calls)

    def clear_highlights(self, nodes, buf):
        logger.debug('clear %d highlights', len(nodes))
        if not nodes:
            return
        # Don't specify line range to clear explicitly because we can't
        # reliably determine the correct range
        calls = [('nvim_buf_clear_highlight',
                  (buf, n.id, 0, -1)) for n in nodes]
        self.call_atomic_async(calls)

    def call_atomic_async(self, calls):
        # Need to update in small batches to avoid
        # https://github.com/neovim/python-client/issues/310
        batch_size = 3000
        for i in range(0, len(calls), batch_size):
            self.vim.api.call_atomic(calls[i:i + batch_size], async=True)
