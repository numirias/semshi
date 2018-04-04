import neovim

from .handler import BufferHandler
from .node import groups
from .util import logger


pattern = '*.py'


def if_enabled(func):
    def wrapper(self):
        if self.active is None:
            self.active = self.vim.eval('get(g:, \'semshi#enabled\', 0)')
        if not self.active:
            return
        func(self)
    return wrapper


@neovim.plugin
class Plugin:

    def __init__(self, vim):
        self.vim = vim
        self.active = None
        self.handlers = {}
        self.current_handler = None
        self._exclude = None

    @neovim.autocmd('VimEnter', pattern=pattern, sync=False)
    def event_vim_enter(self):
        excluded = self.vim.eval('g:semshi#excluded_groups')
        self._exclude = [groups[e] for e in excluded]

    @neovim.autocmd('BufEnter', pattern=pattern, sync=False)
    @if_enabled
    def event_buf_enter(self):
        self.switch_handler()
        # TODO set these elsewehere and just once
        self.update_viewport()
        self.current_handler.update()

    @neovim.autocmd('VimResized', pattern=pattern, sync=False)
    @if_enabled
    def event_vim_resized(self):
        self.visible_area_changed()

    @neovim.autocmd('TextChanged', pattern=pattern, sync=False)
    @if_enabled
    def event_text_changed(self):
        self.current_handler.update()

    @neovim.autocmd('TextChangedI', pattern=pattern, sync=False)
    @if_enabled
    def event_text_changed_insert(self):
        self.current_handler.update()

    @neovim.autocmd('CursorMoved', pattern=pattern, sync=False)
    @if_enabled
    def event_cursor_moved(self):
        self.visible_area_changed()
        self.current_handler.mark_selected(self.vim.current.window.cursor)

    @neovim.autocmd('CursorMovedI', pattern=pattern, sync=False)
    @if_enabled
    def event_cursor_moved_insert(self):
        self.visible_area_changed()
        self.current_handler.mark_selected(self.vim.current.window.cursor)

    @neovim.command('Semshi', range='', nargs='*', sync=True)
    def cmd_semshi(self, args, range):
        self.vim.out_write('This is semshi. %s %s\n' % (args, range))

    def visible_area_changed(self):
        self.update_viewport()
        self.current_handler.add_visible_highlights()

    def switch_handler(self):
        buf = self.vim.current.buffer
        try:
            handler = self.handlers[buf]
        except KeyError:
            handler = BufferHandler(self, buf, exclude=self._exclude)
            self.handlers[buf] = handler
        self.current_handler = handler

    def update_viewport(self):
        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        logger.debug('visible %d - %d', start, stop)
        self.current_handler.set_viewport(start, stop)

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
