import ast
import symtable
from .node import Node

from .util import logger, debug_time
from .visitor import Visitor


class UnparsableError(Exception):

    def __init__(self, error):
        super().__init__()
        self.error = error


class Parser:

    def __init__(self, exclude=[]):
        self._excluded = exclude
        self._lines = []
        self._nodes = []

    @debug_time
    def parse(self, code):
        try:
            return self._parse(code)
        except RecursionError as e:
            logger.debug('recursion error')
            raise UnparsableError(e)
        except SyntaxError as e:
            logger.debug('syntax error: %s', e)
            raise UnparsableError(e)

    @debug_time
    def _filter_excluded(self, nodes):
        return [n for n in nodes if n.hl_group not in self._excluded]

    def _parse(self, code):
        """Parse code and return added and removed nodes."""
        new_lines = code.split('\n')
        new_nodes = self._filter_excluded(self._make_nodes(code, new_lines))
        if self._minor_change(self._lines, new_lines):
            add, rem, keep = self._diff(self._nodes, new_nodes)
            self._nodes = keep + add
        else:
            add, rem = new_nodes, self._nodes
            self._nodes = add
        self._lines = new_lines
        logger.debug('nodes: + %d,  - %d', len(add), len(rem))
        return (add, rem)

    def _make_nodes(self, code, lines):
        ast_root = self._make_ast(code)
        st_root = self._make_symtable(code)
        visitor = Visitor(lines, st_root, ast_root)
        visitor()
        return visitor.names

    @debug_time
    def _make_ast(self, code):
        return ast.parse(code)

    @debug_time
    def _make_symtable(self, code):
        return symtable.symtable(code, '?', 'exec')

    @staticmethod
    def _minor_change(old, new):
        """Return whether a minor change between old and new lines occurred.

        A minor change is a change in a single line while the total number of
        lines remains constant.
        """
        if len(old) != len(new):
            return False
        old_iter = iter(old)
        new_iter = iter(new)
        diffs = 0
        try:
            while True:
                old = next(old_iter)
                new = next(new_iter)
                if old != new:
                    diffs += 1
                    if diffs > 1:
                        return False
        except StopIteration:
            return True

    @staticmethod
    @debug_time
    def _diff(old_nodes, new_nodes):
        """Return difference between iterables old_nodes and new_nodes as three
        lists of nodes to add, remove and keep.
        """
        add_iter = iter(sorted(new_nodes))
        rem_iter = iter(sorted(old_nodes))
        add_nodes = []
        rem_nodes = []
        keep_nodes = []
        try:
            add = rem = None
            while True:
                if add == rem:
                    if add is not None:
                        keep_nodes.append(add)
                        # A new node needs to adopt the highlight ID of
                        # corresponding currently highlighted node
                        add.id = rem.id
                    add = rem = None
                    add = next(add_iter)
                    rem = next(rem_iter)
                elif add < rem:
                    add_nodes.append(add)
                    add = None
                    add = next(add_iter)
                elif rem < add:
                    rem_nodes.append(rem)
                    rem = None
                    rem = next(rem_iter)
        except StopIteration:
            if add is not None:
                add_nodes.append(add)
            if rem is not None:
                rem_nodes.append(rem)
            add_nodes += list(add_iter)
            rem_nodes += list(rem_iter)
        return add_nodes, rem_nodes, keep_nodes

    @debug_time
    def node_at(self, cursor):
        """Return node at cursor position."""
        lineno, col = cursor
        for node in self._nodes:
            if node.lineno == lineno and \
               node.col <= col < node.col + len(node.name):
                return node
        return None

    def same_nodes(self, node_or_cursor):
        if isinstance(node_or_cursor, Node):
            current_node = node_or_cursor
        else:
            current_node = self.node_at(node_or_cursor)
            if current_node is None:
                return []

        # TODO Make this an option
        target = current_node.target
        if target is not None:
            current_node = target

        current_name = current_node.name
        base_table = current_node.base_table()
        ref = getattr(current_node, 'ref', None)
        for node in self._nodes:
            if ref:
                if ref == getattr(node, 'ref', None):
                    yield node
                continue
            if node.name != current_name:
                continue
            if node.base_table() == base_table:
                yield node
