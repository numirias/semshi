import threading

from .parser import Parser, UnparsableError
from .util import logger, debug_time
from .node import Node, SELECTED


class BufferHandler:
    """Handler for a buffer.

    The handler runs the parser, adds and removes highlights, keeps tracks of
    which highlights are visible and which ones need to be added or removed.
    """
    def __init__(self, add_hls, clear_hls, code_func, cursor_func, place_sign,
                 unplace_sign, excluded_hl_groups, mark_selected,
                 error_sign, error_sign_delay):
        self._add_hls = add_hls
        self._clear_hls = clear_hls
        self._get_code = code_func
        self._get_cursor = cursor_func
        self._place_sign = place_sign
        self._unplace_sign = unplace_sign
        self._parser = Parser(exclude=excluded_hl_groups)
        self._scheduled = False
        self._view = (0, 0)
        self._update_thread = None
        self._error_timer = None
        # Nodes which are active but pending to be displayed because they are
        # in a currently invisible area.
        self._pending_nodes = []
        # Nodes which are currently marked as a selected. We keep track of them
        # to check if they haven't changed between updates.
        self._selected_nodes = []
        self._mark_selected = mark_selected
        self._error_sign = error_sign
        self._error_sign_delay = error_sign_delay

    def viewport(self, start, stop):
        """Set viewport to line range from `start` to `stop` and add highlights
        that have become visible."""
        range = stop - start
        self._view = (start - range, stop + range)
        self._add_visible_hls()

    def update(self, force=False, sync=False):
        """Update.

        Start a thread which reparses the code, update highlights.
        """
        if sync:
            self._update_step(force=force, sync=True)
            return
        thread = self._update_thread
        # If there is an active update thread...
        if thread is not None and thread.is_alive():
            # ...just make sure sure it runs another time.
            self._scheduled = True
            return
        thread = threading.Thread(target=self._update_loop)
        self._update_thread = thread
        thread.start()

    @debug_time
    def mark_selected(self, cursor):
        """Mark all selected nodes.

        Selected nodes are those with the same name and scope as the one at the
        cursor position.
        """
        # TODO Make async?
        if not self._mark_selected:
            return
        mark_original = bool(self._mark_selected - 1)
        nodes = self._parser.same_nodes(cursor, mark_original)
        start, stop = self._view
        nodes = [n for n in nodes if start <= n.lineno <= stop]
        if nodes == self._selected_nodes:
            return
        self._selected_nodes = nodes
        self._clear_hls(nodes_to_hl(nodes, clear=True, marked=True))
        self._add_hls(nodes_to_hl(nodes, marked=True))

    @debug_time
    def _add_visible_hls(self):
        """Add highlights in the current viewport which have not been applied
        yet."""
        visible, hidden = self._visible_and_hidden(self._pending_nodes)
        self._add_hls(nodes_to_hl(visible))
        self._pending_nodes = hidden

    def _update_loop(self):
        try:
            while True:
                try:
                    self._update_step()
                except UnparsableError:
                    pass
                if not self._scheduled:
                    return
                self._scheduled = False
        except Exception:
            import traceback
            logger.error('Exception: %s', traceback.format_exc())
            raise

    def _update_step(self, force=False, sync=False):
        code = self._get_code(sync)
        add, rem = self._parser.parse(code, force)
        if self._error_sign:
            self._schedule_update_error_sign()
        # Remove nodes to be cleared from pending list
        rem_remaining = list(self._remove_from_pending(rem))
        add_visible, add_hidden = self._visible_and_hidden(add)
        # Add all new but hidden nodes to pending list
        self._pending_nodes += add_hidden
        # Update highlights by adding all new visible nodes and removing all
        # old nodes which have been drawn earlier
        self._update_hls(add_visible, rem_remaining)
        cursor = self._get_cursor(sync)
        self.mark_selected(cursor)

    def _visible_and_hidden(self, nodes):
        """Bisect nodes into visible and hidden ones."""
        start, end = self._view
        visible = []
        hidden = []
        for node in nodes:
            if start <= node.lineno <= end:
                visible.append(node)
            else:
                hidden.append(node)
        return visible, hidden

    # pylint: disable=protected-access
    @debug_time(None, lambda s, n: ' %d/%d' % (len(n), len(s._pending_nodes)))
    def _remove_from_pending(self, nodes):
        for node in nodes:
            try:
                self._pending_nodes.remove(node)
            except ValueError:
                yield node

    @debug_time(None, lambda _, a, c: '+%d, -%d' % (len(a), len(c)))
    def _update_hls(self, add, clear):
        self._add_hls(nodes_to_hl(add))
        self._clear_hls(nodes_to_hl(clear, clear=True))

    def _schedule_update_error_sign(self):
        if self._error_timer is not None:
            self._error_timer.cancel()
        # If no error is present...
        if self._parser.syntax_error is None:
            # ... but previously was...
            if self._parser.prev_syntax_error is not None:
                # ... update immediately.
                self._update_error_sign()
            # If the current and previous update happened without syntax
            # errors, no action is required.
            return
        # Otherwise, defer update to prevent the sign from frequently showing
        # up while typing.
        timer = threading.Timer(self._error_sign_delay,
                                self._update_error_sign)
        self._error_timer = timer
        timer.start()

    def _update_error_sign(self):
        self._unplace_sign(314000)
        error = self._parser.syntax_error
        if error is None:
            return
        self._place_sign(314000, error.lineno, 'semshiError')


def nodes_to_hl(nodes, clear=False, marked=False):
    """Convert list of nodes to highlight tuples which are the arguments to
    neovim's add_highlight/clear_highlight APIs."""
    if clear:
        if marked:
            return (Node.MARK_ID, 0, -1)
        return [(n.id, 0, -1) for n in nodes]
    if marked:
        id = Node.MARK_ID
        return [(id, SELECTED, n.lineno - 1, n.col, n.end) for n in nodes]
    return [(n.id, n.hl_group, n.lineno - 1, n.col, n.end) for n in nodes]
