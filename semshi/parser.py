import ast
from collections import Iterable
from functools import singledispatch
import symtable

from .node import Node
from .util import logger, debug_time
from .visitor import visitor


class UnparsableError(Exception):

    def __init__(self, error):
        super().__init__()
        self.error = error


class Parser:

    def __init__(self, exclude=[]):
        self._excluded = exclude
        self._lines = []
        self._nodes = []
        self.same_nodes = singledispatch(self.same_nodes)
        self.same_nodes.register(Iterable, self._same_nodes_cursor)

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
        """Parse code and return added and removed nodes since last run."""
        new_lines = code.split('\n')
        new_nodes = self._filter_excluded(self._make_nodes(code, new_lines))
        if self._minor_change(self._lines, new_lines):
            add, rem, keep = self._diff(self._nodes, new_nodes)
            self._nodes = keep + add
        else:
            add, rem = new_nodes, self._nodes
            self._nodes = add
        self._lines = new_lines
        logger.debug('nodes: +%d,  -%d', len(add), len(rem))
        return (add, rem)

    def _make_nodes(self, code, lines=None):
        """Return nodes in code.

        Runs AST visitor on code and produces nodes.
        """
        if lines is None:
            lines = code.split('\n')
        ast_root = self._make_ast(code)
        symtable_root = self._make_symtable(code)
        return visitor(lines, symtable_root, ast_root)

    @debug_time
    def _make_ast(self, code):
        """Return AST for code."""
        return ast.parse(code)

    @debug_time
    def _make_symtable(self, code):
        """Return symtable for code."""
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
            if node.lineno == lineno and node.col <= col < node.end:
                return node
        return None

    def same_nodes(self, cur_node):
        """Return nodes with the same scope as cur_node.

        The same scope is to be understood as all nodes with the same base
        symtable. In some cases this can be ambiguous.
        """
        # TODO Make this an option
        target = cur_node.target
        if target is not None:
            cur_node = target
        cur_name = cur_node.name
        base_table = cur_node.base_table()
        ref = getattr(cur_node, 'ref', None)
        for node in self._nodes:
            if ref is not None:
                if ref == getattr(node, 'ref', None):
                    yield node
                continue
            if node.name != cur_name:
                continue
            if node.base_table() == base_table:
                yield node

    def _same_nodes_cursor(self, cursor):
        """Return nodes with the same scope as node at the cursor position."""
        cur_node = self.node_at(cursor)
        if cur_node is None:
            return []
        return self.same_nodes(cur_node)
