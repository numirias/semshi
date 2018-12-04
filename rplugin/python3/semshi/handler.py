from collections import defaultdict
from fnmatch import fnmatch
import threading
import time

try:
    import pynvim as neovim
except ImportError:
    import neovim

from .parser import Parser, UnparsableError
from .util import logger, debug_time, lines_to_code
from .node import Node, SELECTED


ERROR_SIGN_ID = 314000
ERROR_HL_ID = 313000


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
        self._indicated_syntax_error = None
        # Nodes which are active but pending to be displayed because they are
        # in a currently invisible area.
        self._pending_nodes = []
        # Nodes which are currently marked as a selected. We keep track of them
        # to check if they haven't changed between updates.
        self._selected_nodes = []
        self.enabled = not any(fnmatch(buf.name, pattern) for pattern in
                               self._options.excluded_buffers)

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

        If `sync`, trigger update immediately, otherwise start thread to update
        code if thread isn't running already.
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

    def clear_highlights(self):
        """Clear all highlights."""
        self._update_step(force=True, sync=True, code='')

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
        block until result is available.

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

    def _wrap_async(self, func):
        """
        Wraps `func` so that invocation of `func(args, kwargs)` happens
        from the main thread. This is a requirement of neovim API when
        function call happens from other threads.
        Related issue: https://github.com/numirias/semshi/issues/25
        """
        def wrapper(*args, **kwargs):
            return self._vim.async_call(func, *args, **kwargs)
        return wrapper

    def _update_loop(self):
        try:
            while True:
                delay_factor = self._options.update_delay_factor
                if delay_factor > 0:
                    time.sleep(delay_factor * len(self._parser.lines))
                self._update_step(self._options.always_update_all_highlights)
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
    def _update_step(self, force=False, sync=False, code=None):
        """Trigger parser, update highlights accordingly, and trigger update of
        error sign.
        """
        if code is None:
            code = self._wait_for(lambda: lines_to_code(self._buf[:]), sync)
        try:
            add, rem = self._parser.parse(code, force)
        except UnparsableError:
            pass
        else:
            # TODO If we force update, can't we just clear all pending?
            # Remove nodes to be cleared from pending list
            rem_remaining = debug_time('remove from pending')(
                lambda: list(self._remove_from_pending(rem)))()
            add_visible, add_hidden = self._visible_and_hidden(add)
            # Add all new but hidden nodes to pending list
            self._pending_nodes += add_hidden
            # Update highlights by adding all new visible nodes and removing
            # all old nodes which have been drawn earlier
            self._update_hls(add_visible, rem_remaining)
            self.mark_selected(
                self._wait_for(lambda: self._vim.current.window.cursor, sync))
        if self._options.error_sign:
            self._schedule_update_error_sign()

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
        if self._indicated_syntax_error is not None:
            self._update_error_indicator()
            return
        # Delay update to prevent the error sign from flashing while typing.
        timer = threading.Timer(self._options.error_sign_delay,
                                self._update_error_indicator)
        self._error_timer = timer
        timer.start()

    def _update_error_indicator(self):
        cur_error = self._indicated_syntax_error
        error = self._parser.syntax_errors[-1]
        self._indicated_syntax_error = error
        if cur_error is not None and error is not None and \
           (error.lineno, error.offset, error.msg) == \
           (cur_error.lineno, cur_error.offset, cur_error.msg):
            return
        self._unplace_sign(ERROR_SIGN_ID)
        self._wrap_async(self._buf.clear_highlight)(ERROR_HL_ID)
        if error is None:
            return
        self._place_sign(ERROR_SIGN_ID, error.lineno, 'semshiError')
        lineno, offset = self._error_pos(error)
        self._wrap_async(self._buf.add_highlight)(
            'semshiErrorChar',
            lineno - 1,
            offset,
            offset + 1,
            ERROR_HL_ID,
        )

    def _place_sign(self, id, line, name):
        self._wrap_async(self._vim.command)(
            'sign place %d line=%d name=%s buffer=%d' % (
                id, line, name, self._buf_num),
            async_=True)

    def _unplace_sign(self, id):
        self._wrap_async(self._vim.command)(
            'sign unplace %d buffer=%d' % (
                id, self._buf_num),
            async_=True)

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
            self._wrap_async(buf.clear_highlight)(*node_or_nodes)
            return
        # Don't specify line range to clear explicitly because we can't
        # reliably determine the correct range
        self._call_atomic_async(
            [('nvim_buf_clear_highlight', (buf, *n)) for n in node_or_nodes])

    def _call_atomic_async(self, calls):
        # Need to update in small batches to avoid
        # https://github.com/neovim/python-client/issues/310
        batch_size = 3000
        call_atomic = self._wrap_async(self._vim.api.call_atomic)
        for i in range(0, len(calls), batch_size):
            call_atomic(calls[i:i + batch_size], async_=True)

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

    def goto(self, what, direction=None):
        """Go to next location of type `what` in direction `direction`."""
        if what == 'error':
            self._goto_error()
            return
        from ast import ClassDef, FunctionDef, AsyncFunctionDef
        here = tuple(self._vim.current.window.cursor)
        if what == 'name':
            cur_node = self._parser.node_at(here)
            if cur_node is None:
                return
            locs = sorted([n.pos for n in self._parser.same_nodes(
                cur_node, use_target=self._options.self_to_attribute)])
        elif what == 'class':
            locs = self._parser.locations_of([ClassDef])
        elif what == 'function':
            locs = self._parser.locations_of([FunctionDef, AsyncFunctionDef])
        else:
            raise ValueError('"%s" is not a recognized element type.' % what)
        if direction == 'first':
            new_loc = locs[0]
        elif direction == 'last':
            new_loc = locs[-1]
        else:
            new_loc = next_location(here, locs, (direction == 'prev'))
        try:
            self._vim.current.window.cursor = new_loc
        except neovim.api.NvimError:
            # This can happen when the new cursor position is outside the
            # buffer because the code wasn't re-parsed after a buffer change.
            pass

    def _goto_error(self):
        """Go to syntax error."""
        error = self._indicated_syntax_error
        if error is None:
            return
        self._vim.current.window.cursor = self._error_pos(error)

    def _error_pos(self, error):
        """Return a position for the syntax error `error` which is guaranteed
        to be a valid position in the buffer."""
        offset = max(1, min(error.offset,
                            len(self._parser.lines[error.lineno - 1]))) - 1
        return (error.lineno, offset)

    def show_error(self):
        error = self._indicated_syntax_error
        if error is None:
            self._vim.out_write('No syntax error to show.\n')
            return
        self._vim.out_write('Syntax error: %s (%d, %d)\n' %
                            (error.msg, error.lineno, error.offset))

    def shutdown(self):
        # Cancel the error timer so vim quits immediately
        if self._error_timer is not None:
            self._error_timer.cancel()


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


def next_location(here, locs, reverse=False):
    """Return the location of `locs` that comes after `here`."""
    locs = locs[:]
    if here not in locs:
        locs.append(here)
    locs = sorted(locs)
    return locs[(locs.index(here) + (-1 if reverse else 1)) % len(locs)]
