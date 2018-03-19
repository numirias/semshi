from queue import Queue
import threading

from .parser import Parser, UnparsableError
from .util import logger, debug_time
from .node import Node


# class AlreadyRunning(Exception):
#     pass


class BufferHandler:

    def __init__(self, plugin, buffer, exclude=None):
        self.plugin = plugin
        self.buf = buffer
        self.scheduled = False
        self.view_start = 0
        self.view_stop = 0
        self.add_pending = []
        self.parser = Parser(exclude=exclude)
        self._thread = None

    def set_viewport(self, start, stop):
        range = (stop - start)
        self.view_start = start - range
        self.view_stop = stop + range

    def update(self):
        thread = self._thread
        if thread is not None and thread.is_alive():
            logger.debug('update scheduled')
            self.scheduled = True
            return
        thread = threading.Thread(target=self._update_loop)
        self._thread = thread
        thread.start()

    def _update_loop(self):
        try:
            while True:
                try:
                    self._update()
                except UnparsableError:
                    pass
                if not self.scheduled:
                    return
                self.scheduled = False
        except:
            import traceback
            logger.error('exception: %s', traceback.format_exc())

    def _update(self):
        code = self._current_code()
        names_add, names_clear = self.parser.parse(code)

        # Remove nodes from add_pending which should be cleared
        self._remove_pending_names(names_clear)

        visible_add, hidden_add = self._visible_and_hidden(names_add)
        # Add new adds which aren't visible to pending
        self.add_pending += hidden_add

        self.update_highlights(visible_add, names_clear)

    def _visible_and_hidden(self, nodes):
        start, end = self.view_start, self.view_stop
        visible = []
        hidden = []
        for node in nodes:
            if start <= node.lineno <= end:
                visible.append(node)
            else:
                hidden.append(node)
        return visible, hidden

    @debug_time('get current code')
    def _current_code(self):
        queue = Queue()
        self.plugin.vim.async_call(lambda: queue.put(self.buf[:]))
        lines = queue.get()
        code = '\n'.join(lines)
        return code

    @debug_time('remove pending')
    def _remove_pending_names(self, names):
        for name in names:
            try:
                self.add_pending.remove(name)
            except ValueError:
                pass

    @debug_time('hl update', lambda _, a, c: '+%d, -%d' % (len(a), len(c)))
    def update_highlights(self, add, clear):
        # logger.debug('add %d, clear %d', len(add), len(clear))
        self.plugin.add_highlights(add, self.buf)
        self.plugin.clear_highlights(clear, self.buf)

    def add_visible_highlights(self):
        """Add highlights in the current viewport which have not been applied
        yet."""
        add_now, self.add_pending = self._visible_and_hidden(self.add_pending)
        self.plugin.add_highlights(add_now, self.buf)

    @debug_time('mark names')
    def mark_selected(self, cursor):
        # TODO Make async?
        start = self.view_start
        stop = self.view_stop
        buf = self.buf
        nodes = list(self.parser.same_nodes(cursor))
        nodes = [node for node in nodes if start <= node.lineno <= stop]
        buf.clear_highlight(Node.MARK_ID)
        for node in nodes:
            buf.add_highlight(*node.hl(marked=True))

