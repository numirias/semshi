from collections import defaultdict
import threading
import time

from .parser import Parser, UnparsableError
from .util import logger, debug_time, lines_to_code
from .node import Node, SELECTED


ERROR_SIGN_ID = 314000


class BufferHandler:
    """Handler for a buffer.

    The handler runs the parser, adds and removes highlights, keeps tracks of
    which highlights are visible and which ones need to be added or removed.
    """
    def __init__(self, buf, vim, options):
        self._buf = buf
        self._vim = vim
        self._options = options
        self._buf_num = buf.number
        self._parser = Parser(options.excluded_hl_groups,
                              options.tolerate_syntax_errors)
        self._scheduled = False
        self._viewport_changed = False
        self._view = (0, 0)
        self._update_thread = None
        self._error_timer = None
        # Nodes which are active but pending to be displayed because they are
        # in a currently invisible area.
        self._pending_nodes = []
        # Nodes which are currently marked as a selected. We keep track of them
        # to check if they haven't changed between updates.
        self._selected_nodes = []

    def viewport(self, start, stop):
        """Set viewport to line range from `start` to `stop` and add highlights
        that have become visible."""
        range = stop - start
        self._view = (start - range, stop + range)
        # If the update thread is running, we defer addding visible highlights
        # for the new viewport to after the update loop is done.
        if self._update_thread is not None and self._update_thread.is_alive():
            self._viewport_changed = True
            return
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
        # Otherwise, start a new update thread.
        thread = threading.Thread(target=self._update_loop)
        self._update_thread = thread
        thread.start()

    @debug_time
    def mark_selected(self, cursor):
        """Mark all selected nodes.

        Selected nodes are those with the same name and scope as the one at the
        cursor position.
        """
        if not self._options.mark_selected_nodes:
            return
        mark_original = bool(self._options.mark_selected_nodes - 1)
        nodes = self._parser.same_nodes(cursor, mark_original,
                                        self._options.self_to_attribute)
        start, stop = self._view
        nodes = [n for n in nodes if start <= n.lineno <= stop]
        if nodes == self._selected_nodes:
            return
        self._selected_nodes = nodes
        self._clear_hls(nodes_to_hl(nodes, clear=True, marked=True))
        self._add_hls(nodes_to_hl(nodes, marked=True))

    def _wait_for(self, func, sync=False):
        """Return `func()`. If not `sync`, run `func` in async context and
        block until result is received.

        Required for when we need the result of an API call from a thread.
        """
        if sync:
            return func()
        event = threading.Event()
        res = None
        def wrapper():
            nonlocal res
            res = func()
            event.set()
        self._vim.async_call(wrapper)
        event.wait()
        return res

    def _update_loop(self):
        try:
            while True:
                self._update_step(self._options.always_update_all_highlights)
                if self._options.error_sign:
                    self._schedule_update_error_sign()
                if not self._scheduled:
                    break
                self._scheduled = False
            if self._viewport_changed:
                self._add_visible_hls()
                self._viewport_changed = False
        except Exception:
            import traceback
            logger.error('Exception: %s', traceback.format_exc())
            raise

    @debug_time
    def _update_step(self, force=False, sync=False):
        delay_factor = self._options.update_delay_factor
        if delay_factor > 0:
            time.sleep(delay_factor * len(self._parser.lines))
        try:
            add, rem = self._parser.parse(
                self._wait_for(lambda: lines_to_code(self._buf[:]), sync),
                force,
            )
        except UnparsableError:
            return
        # TODO If we force update, can't we just clear all pending?
        # Remove nodes to be cleared from pending list
        rem_remaining = debug_time('remove from pending')(
            lambda: list(self._remove_from_pending(rem)))()
        add_visible, add_hidden = self._visible_and_hidden(add)
        # Add all new but hidden nodes to pending list
        self._pending_nodes += add_hidden
        # Update highlights by adding all new visible nodes and removing all
        # old nodes which have been drawn earlier
        self._update_hls(add_visible, rem_remaining)
        self.mark_selected(
            self._wait_for(lambda: self._vim.current.window.cursor, sync))

    @debug_time
    def _add_visible_hls(self):
        """Add highlights in the current viewport which have not been applied
        yet."""
        visible, hidden = self._visible_and_hidden(self._pending_nodes)
        self._add_hls(nodes_to_hl(visible))
        self._pending_nodes = hidden

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
    @debug_time(None, lambda s, n: '%d / %d' % (len(n), len(s._pending_nodes)))
    def _remove_from_pending(self, nodes):
        """Return nodes which couldn't be removed from the pending list (which
        means they need to be cleared from the buffer).
        """
        for node in nodes:
            try:
                self._pending_nodes.remove(node)
            except ValueError:
                # TODO Can we maintain a list of nodes that should be active
                # instead of creating it here?
                yield node

    def _schedule_update_error_sign(self):
        if self._error_timer is not None:
            self._error_timer.cancel()
        # If no error is present...
        if self._parser.syntax_errors[-1] is None:
            # ... but previously was...
            if self._parser.syntax_errors[-2] is not None:
                # ... update immediately.
                self._update_error_sign()
            # If the current and previous update happened without syntax
            # errors, no action is required.
            return
        # Otherwise, delay update to prevent the sign from frequently flashing
        # while typing.
        timer = threading.Timer(self._options.error_sign_delay,
                                self._update_error_sign)
        self._error_timer = timer
        timer.start()

    def _update_error_sign(self):
        self._unplace_sign(ERROR_SIGN_ID)
        error = self._parser.syntax_errors[-1]
        if error is None:
            return
        self._place_sign(ERROR_SIGN_ID, error.lineno, 'semshiError')

    def _place_sign(self, id, line, name):
        self._vim.command('sign place %d line=%d name=%s buffer=%d' %
                          (id, line, name, self._buf_num), async=True)

    def _unplace_sign(self, id):
        self._vim.command('sign unplace %d buffer=%d' %
                          (id, self._buf_num), async=True)

    @debug_time(None, lambda _, a, c: '+%d, -%d' % (len(a), len(c)))
    def _update_hls(self, add, clear):
        self._add_hls(nodes_to_hl(add))
        self._clear_hls(nodes_to_hl(clear, clear=True))

    @debug_time(None, lambda _, nodes: '%d nodes' % len(nodes))
    def _add_hls(self, node_or_nodes):
        buf = self._buf
        if not node_or_nodes:
            return
        if not isinstance(node_or_nodes, list):
            buf.add_highlight(*node_or_nodes)
            return
        self._call_atomic_async(
            [('nvim_buf_add_highlight', (buf, *n)) for n in node_or_nodes])

    @debug_time(None, lambda _, nodes: '%d nodes' % len(nodes))
    def _clear_hls(self, node_or_nodes):
        buf = self._buf
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
            self._vim.api.call_atomic(calls[i:i + batch_size], async=True)

    def rename(self, cursor, new_name=None):
        """Rename node at `cursor` to `new_name`. If `new_name` is None, prompt
        for new name."""
        cur_node = self._parser.node_at(cursor)
        if cur_node is None:
            self._vim.out_write('Nothing to rename here.\n')
            return
        nodes = list(self._parser.same_nodes(
            cur_node,
            mark_original=True,
            use_target=self._options.self_to_attribute,
        ))
        num = len(nodes)
        if new_name is None:
            new_name = self._vim.eval('input("Rename %d nodes to: ")' % num)
            # Can't output a carriage return via out_write()
            self._vim.command('echo "\r"')
        if not new_name or new_name == cur_node.name:
            self._vim.out_write('Nothing renamed.\n')
            return
        lines = self._buf[:]
        lines_to_nodes = defaultdict(list)
        for node in nodes:
            lines_to_nodes[node.lineno].append(node)
        for lineno, nodes_in_line in lines_to_nodes.items():
            offset = 0
            line = lines[lineno - 1]
            for node in sorted(nodes_in_line, key=lambda n: n.col):
                line = (line[:node.col + offset] + new_name +
                        line[node.col + len(node.name) + offset:])
                offset += len(new_name) - len(node.name)
            self._buf[lineno - 1] = line
        self._vim.out_write('%d nodes renamed.\n' % num)

    def next_location(self, kind, location, reverse=False):
        """Return the location of the next node after node at `location`.
        """
        from ast import ClassDef, FunctionDef, AsyncFunctionDef
        if kind == 'name':
            cur_node = self._parser.node_at(location)
            if cur_node is None:
                raise ValueError('No node at cursor.')
            locs = [n.pos for n in self._parser.same_nodes(
                cur_node, use_target=self._options.self_to_attribute)]
        elif kind == 'class':
            locs = self._parser.locations([ClassDef])
        elif kind == 'function':
            locs = self._parser.locations([FunctionDef, AsyncFunctionDef])
        else:
            raise ValueError('"%s" is not a recognized element type.' % kind)
        return next_location(tuple(location), locs, reverse)


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


def next_location(here, all, reverse=False):
    """Return the location from `all` that comes after `here`."""
    all = all[:]
    if here not in all:
        all.append(here)
    all = sorted(all)
    return all[(all.index(here) + (-1 if reverse else 1)) % len(all)]
