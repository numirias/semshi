import threading
import time
from queue import Queue

import neovim

from .parser import Parser, UnparsableError
from .node import LOCAL, IMPORTED, Node
from .util import logger, debug_time



pattern  = '*.py'


class AlreadyRunning(Exception):
    pass


class BufferHandler:

    def __init__(self, plugin, buffer):
        self.plugin = plugin
        self.buf = buffer
        self.running = False
        self.scheduled = False
        self.vis_start = 0
        self.vis_end = 0
        self.names_add = []
        self.parser = Parser(exclude=[LOCAL])
        # self.queue = Queue()
        self.event = threading.Event()
        self.lines = []

    def set_visible_range(self, start, stop):
        range = (stop - start)
        self.vis_start = start - range
        self.vis_end = stop + range


    def load_buffer_content(self):
        x = self.buf[:]
        self.lines = x
        self.p = time.time()
        self.event.set()
        # self.queue.put(x)
        logger.debug('got %d', len(x))

    def parse(self):
        if self.running:
            logger.debug('already running!')
            self.scheduled = True
            return
            # raise AlreadyRunning()
        self.running = True

        # TODO how long does a thread take to start?
        thread = threading.Thread(target=self.parse_thread)
        thread.start()

    def parse_thread(self):
        logger.debug('PARSE!')
        self.plugin.vim.async_call(self.load_buffer_content)

        self.event.wait()
        self.event.clear()
        lines = self.lines
        # lines = self.queue.get()
        logger.debug('QUEUE TIME %f', time.time() - self.p)

        # logger.debug('START')
        current_buffer = lines
        code = '\n'.join(current_buffer) # TODO add \n ?
        logger.debug('current buffer %d', len(current_buffer))
        try:
            names_add, names_clear = self.parser.parse(code)
        except UnparsableError:
            self.running = False
            return
        else:
            # self.hide_error()
            pass

        self.clear_names(names_clear)

        start, end = self.vis_start, self.vis_end
        names_add_now = []
        for name in names_add:
            if start <= name.lineno <= end:
                names_add_now.append(name)
            else:
                self.names_add.append(name)
                # logger.debug('names_add %s', name)

        # names_clear_now = names_clear
        # names_add_now = names_add

        # names_add = [node for node in names_add if start <= node.lineno <= end]
        # names_clear = [node for node in names_clear if start <= node.lineno <= end]

        self.update_highlights(names_add_now, names_clear)

        # TODO re-enable
        if self.scheduled:
            self.scheduled = False
            self.parse_thread()
        else:
            self.running = False

    @debug_time('remove pending')
    def clear_names(self, names):
        for name in names:
            try:
                self.names_add.remove(name)
            except ValueError:
                pass

    @debug_time('hl update')
    def update_highlights(self, add, clear):
        # TODO don't call for empty lists
        self.plugin.add_highlights(add, self.buf)
        # logger.debug('CLEARING %d', len(names_clear))
        self.plugin.clear_highlights(clear, self.buf)

    def add_visible_highlights(self):
        start, end = self.vis_start, self.vis_end
        logger.debug('visible %d - %d', start, end)

        names_add_remain = []
        names_add_now = []
        for name in self.names_add:
            if start <= name.lineno <= end:
                names_add_now.append(name)
            else:
                names_add_remain.append(name)

        self.names_add = names_add_remain

        return names_add_now

    def remove_from_pending_add(self, name):
        # TODO this takes too long. maybe when names got completely refreshed just clear all
        try:
            self.names_add.remove(name)
        except ValueError:
            pass
            # logger.debug('don\'t need to remove %s', name)
        else:
            pass
            # logger.debug('found and removed %s', name)

    def mark_names(self, start, stop, cursor):
        # logger.debug('start %s', type(start))
        buf = self.buf
        # t = time.time()
        nodes = list(self.parser.same_nodes(cursor))
        nodes = [node for node in nodes if start <= node.lineno <= stop]
        buf.clear_highlight(Node.MARK_ID)
        for node in nodes:
            # logger.debug('adding %s', node)
            buf.add_highlight(*node.hl(marked=True))
        # logger.debug('%d same nodes %f', len(nodes), time.time() - t)


@neovim.plugin
class Plugin:

    def __init__(self, vim):
        self.vim = vim
        self.handlers = {}
        self.active = False
        self.error_sign = False
        # Needs to be implemented per-parser

    def set_visible_range(self):
        # TODO don't set when changed
        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        self.current_buffer().set_visible_range(start, stop)

    @neovim.autocmd('TextChanged', pattern=pattern, sync=False)
    def text_changed(self):
        if not self.active:
            return
        self.set_visible_range()
        self.parse()

    @neovim.autocmd('TextChangedI', pattern=pattern, sync=False)
    def text_changed_insert(self):
        if not self.active:
            return
        self.set_visible_range()
        self.parse()

    # TODO Handle vim resized for visible_highlights()

    @neovim.autocmd('CursorMoved', pattern=pattern, sync=False)
    def autocmd_handler4(self):
        if not self.active:
            return
        # logger.debug('cursor moved')
        self.set_visible_range()
        names = self.current_buffer().add_visible_highlights()
        self.add_highlights(names, self.vim.current.buffer)

        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        cursor = self.vim.current.window.cursor
        self.current_buffer().mark_names(start, stop, cursor)

    @neovim.autocmd('CursorMovedI', pattern=pattern, sync=False)
    def autocmd_handler5(self):
        if not self.active:
            return
        # logger.debug('cursor moved i')
        self.set_visible_range()
        names = self.current_buffer().add_visible_highlights()
        self.add_highlights(names, self.vim.current.buffer)

        start = self.vim.eval('line("w0")')
        stop = self.vim.eval('line("w$")')
        cursor = self.vim.current.window.cursor
        self.current_buffer().mark_names(start, stop, cursor)

    @neovim.autocmd('BufEnter', pattern=pattern, sync=False)
    def buf_enter(self):
        self.active = self.vim.eval('get(g:, \'semshi_enabled\', 0)')
        if not self.active:
            return
        # TODO set these elsewehere and just once
        self.set_visible_range()
        self.parse()

    @neovim.command('Semshi', range='', nargs='*', sync=True)
    def ps(self, args, range):
        self.vim.out_write('This is semshi.\n')

    def current_buffer(self):
        buf = self.vim.current.buffer
        try:
            handler = self.handlers[buf]
        except KeyError:
            # handler = Parser(exclude=[LOCAL]) # TODO exclusion doesn't work
            handler = BufferHandler(self, buf)
            self.handlers[buf] = handler
        return handler

    def parse(self):
        handler = self.current_buffer()
        handler.parse()

    def add_highlights(self, names_add, buf):
        logger.debug('ADD HL %s', len(names_add))
        # logger.debug('ADD HL %s', names_add)
        # for node in names_add:
        #     # logger.debug('adding %s %d', node, node.id)
        #     buf.add_highlight(*node.hl(), async=True)
        if names_add:
            t2 = time.time()
            reqs = [
                ('nvim_buf_add_highlight', (buf, node.id, node.hl_group, node.lineno - 1, node.col, node.end)) for node in names_add
            ]
            res = self.vim.api.call_atomic(reqs, async=True)
            # logger.debug('add %s', res)
            logger.debug('ATOMIC %f', time.time() - t2)

    def clear_highlights(self, names_clear, buf):
        logger.debug('CLEAR HL %s', len(names_clear))
        # logger.debug('CLEAR HL %s', names_clear)
        # for node in names_clear:
        #     # logger.debug('clearing %s %d', node, node.id)
        #     buf.clear_highlight(node.id)
        if names_clear:
            reqs = [
                # TODO which one is faster? (first one gives error for fast ops)
                # ('nvim_buf_clear_highlight', (buf, node.id, node.lineno-1, node.lineno)) for node in names_clear
                ('nvim_buf_clear_highlight', (buf, node.id, 0, -1)) for node in names_clear
            ]

            amt = 3000
            for i in range(0, len(reqs), amt):
                res = self.vim.api.call_atomic(reqs[i:i+amt], async=True)
            # res = self.vim.api.call_atomic(reqs, async=True)
            # logger.debug('rem %s', res)


    def show_error(self, e):
        if not self.error_sign:
            return
        logger.debug(e.lineno)
        num = self.vim.current.buffer.number
        self.vim.command('sign place %d line=%d name=%s buffer=%s' %
                         (314000, e.lineno, 'semshiError', num), async=True)

    def hide_error(self):
        if not self.error_sign:
            return
        self.vim.command('sign unplace %d' % 314000, async=True)
