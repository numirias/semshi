import threading

from .parser import Parser, UnparsableError
from .util import logger, debug_time
from .node import Node


class BufferHandler:

    def __init__(self, plugin, buffer):
        self.plugin = plugin
        self.buf = buffer
        self.scheduled = False
        self._view = (0, 0)
        self.add_pending = []
        self._parser = Parser(exclude=self.plugin.options.excluded_hl_groups)
        self._thread = None
        self._selected_nodes = []
        self._mark_original_node = self.plugin.options.mark_original_node

    def set_viewport(self, start, stop): # TODO make assignment
        range = stop - start
        self._view = (start - range, stop + range)

    def update(self):
        """Update.

        Start a thread which reparses the code, updates highlights.
        """
        thread = self._thread
        if thread is not None and thread.is_alive():
            self.scheduled = True
            return
        thread = threading.Thread(target=self._update_loop)
        self._thread = thread
        thread.start()

    def _update_loop(self):
        try:
            while True:
                try:
                    self._update_step()
                except UnparsableError:
                    pass
                if not self.scheduled:
                    return
                self.scheduled = False
        except Exception:
            import traceback
            logger.error('exception: %s', traceback.format_exc())
            raise

    def _update_step(self):
        code = self._current_code()
        add, rem = self._parser.parse(code)
        # Remove nodes from add_pending which should be cleared anyway
        remaining = list(self._remove_from_pending(rem))
        logger.debug('remaining %d', len((remaining)))
        visible_add, hidden_add = self._visible_and_hidden(add)
        # Add new adds which aren't visible to pending
        self.add_pending += hidden_add
        self.update_highlights(visible_add, remaining)
        cursor = self._wait_for(lambda: self.plugin.vim.current.window.cursor)
        self.mark_selected(cursor)

    def _visible_and_hidden(self, nodes):
        start, end = self._view
        visible = []
        hidden = []
        for node in nodes:
            if start <= node.lineno <= end:
                visible.append(node)
            else:
                hidden.append(node)
        return visible, hidden

    def _wait_for(self, func):
        """Run func asynchronously, block until done and return result."""
        event = threading.Event()
        res = None
        def wrapper():
            nonlocal res
            res = func()
            event.set()
        self.plugin.vim.async_call(wrapper)
        event.wait()
        return res

    @debug_time
    def _current_code(self):
        """Return current buffer content."""
        lines = self._wait_for(lambda: self.buf[:])
        code = '\n'.join(lines)
        return code

    @debug_time(None, lambda s, n: ' %d/%d' % (len(n), len(s.add_pending)))
    def _remove_from_pending(self, nodes):
        for node in nodes:
            try:
                self.add_pending.remove(node)
            except ValueError:
                yield node

    @debug_time(None, lambda _, a, c: '+%d, -%d' % (len(a), len(c)))
    def update_highlights(self, add, clear):
        # logger.debug('add %d, clear %d', len(add), len(clear))
        self.plugin.add_highlights([a.hl() for a in add], self.buf)
        self.plugin.clear_highlights(clear, self.buf)

    def add_visible_highlights(self):
        """Add highlights in the current viewport which have not been applied
        yet."""
        add, self.add_pending = self._visible_and_hidden(self.add_pending)
        self.plugin.add_highlights([a.hl() for a in add], self.buf)

    @debug_time
    def mark_selected(self, cursor):
        # TODO Make async?
        nodes = self._parser.same_nodes(cursor, self._mark_original_node)
        start, stop = self._view
        nodes = [n for n in nodes if start <= n.lineno <= stop]
        if nodes == self._selected_nodes:
            return
        self._selected_nodes = nodes
        self.buf.clear_highlight(Node.MARK_ID)
        self.plugin.add_highlights([n.hl(True) for n in nodes], self.buf)
