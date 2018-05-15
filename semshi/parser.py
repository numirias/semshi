import ast
from collections import Iterable
from functools import singledispatch
from keyword import kwlist
import symtable
from token import NAME, INDENT, OP
from tokenize import TokenError, tokenize

from .util import debug_time, logger
from .visitor import visitor


class UnparsableError(Exception):

    def __init__(self, error):
        super().__init__()
        self.error = error


class Parser:

    def __init__(self, exclude=None, fix_syntax=True):
        self._excluded = exclude or []
        self._fix_syntax = fix_syntax
        self._nodes = []
        self.lines = []
        # Incremented after every parse call
        self.tick = 0
        # Holds the SyntaxError exception of the current run
        self.syntax_error = None
        # Holds the error of the previous run, so the buffer handler knows if
        # error signs need to be updated
        self.prev_syntax_error = None
        self.same_nodes = singledispatch(self.same_nodes)
        self.same_nodes.register(Iterable, self._same_nodes_cursor)

    @debug_time
    def parse(self, code, force=False):
        """Parse code and return tuple (add, remove) of added and removed nodes
        since last run.

        Raises UnparsableError() if unrecoverable error occurred.
        """
        # TODO Refactor SyntaxError/UnparsableError mechanics
        try:
            res = self._parse(code, force)
            self.tick += 1
            return res
        except (SyntaxError, RecursionError) as e:
            logger.debug('parsing error: %s', e)
            self.tick += 1
            raise UnparsableError(e)

    @debug_time
    def _filter_excluded(self, nodes):
        return [n for n in nodes if n.hl_group not in self._excluded]

    def _parse(self, code, force):
        """Inner parse function.

        Return tuple (add, remove) of added and removed nodes since last run.
        """
        old_lines = self.lines
        new_lines = code.split('\n')
        minor_change, change_lineno = self._minor_change(old_lines, new_lines)
        # TODO Make exception handling clearer
        new_nodes = self._make_nodes(code, new_lines, change_lineno)
        # Detecting minor changes keeps us from updating a lot of highlights
        # while the user is only editing a single line.
        if not force and minor_change:
            add, rem, keep = self._diff(self._nodes, new_nodes)
            self._nodes = keep + add
        else:
            add, rem = new_nodes, self._nodes
            self._nodes = add
        # Only assign new lines when nodes have been updates accordingly
        self.lines = new_lines
        logger.debug('[%d] nodes: +%d,  -%d', self.tick, len(add), len(rem))
        return (self._filter_excluded(add), self._filter_excluded(rem))

    def _make_nodes(self, code, lines=None, change_lineno=None):
        """Return nodes in code.

        Runs AST visitor on code and produces nodes. We're passing both code
        *and* lines around to avoid lots of conversions.
        """
        if lines is None:
            lines = code.split('\n')
        ast_root, fixed_code, fixed_lines = self._fix_errors(code, lines,
                                                             change_lineno)
        if fixed_code is not None:
            code = fixed_code
            lines = fixed_lines
        try:
            symtable_root = self._make_symtable(code)
        except SyntaxError as e:
            # In some cases, the symtable() call raises a syntax error which
            # hasn't been caught earlier (such as duplicate arguments)
            self.syntax_error = e
            raise
        return visitor(lines, symtable_root, ast_root)

    @debug_time
    def _fix_errors(self, code, lines, change_lineno):
        """Try to fix syntax errors in code (if present) and return AST, fixed
        code and list of fixed lines of code.

        Current strategy to fix syntax errors:
        - Try to build AST from original code.
        - If that fails, call _fix_line() on the line indicated by the
          SyntaxError exception and try to build AST again.
        - If that fails, do the same with the line of the last change.
        - If all attempts failed, raise original SyntaxError exception.
        """
        # TODO Refactor and rename
        # TODO Cache previous attempt?
        self.prev_syntax_error = self.syntax_error
        try:
            self.syntax_error = None
            return self._make_ast(code), None, None
        except SyntaxError as e:
            orig_error = e
            error_idx = e.lineno - 1
        self.syntax_error = orig_error
        if not self._fix_syntax:
            # Don't attempt to fix syntax errors
            raise orig_error
        lines = lines[:] # TODO Do we need a copy?
        orig_line = lines[error_idx]
        lines[error_idx] = self._fix_line(orig_line)
        code = '\n'.join(lines)
        try:
            return self._make_ast(code), code, lines
        except SyntaxError:
            pass
        # Restore original line
        lines[error_idx] = orig_line
        # Replacing the line of the syntax error failed. Now try again with the
        # line of last change.
        if change_lineno is None:
            # Don't know where change occurred, so can't check changed line.
            raise orig_error
        if change_lineno == error_idx:
            # DOn't check a line we already used.
            raise orig_error
        lines[change_lineno] = self._fix_line(lines[change_lineno])
        code = '\n'.join(lines)
        try:
            return self._make_ast(code), code, lines
        except SyntaxError:
            raise orig_error

    @staticmethod
    def _fix_line(line):
        """Take a line of code which may have introduced a syntax error and
        return a modified version which is less likely to cause a syntax error.
        """
        tokens = tokenize(iter([line.encode('utf-8')]).__next__)
        prev = None
        text = ''
        def add_token(token, filler):
            nonlocal text, prev
            text += (token.start[1] - len(text)) * filler + token.string
            prev = token
        try:
            for token in tokens:
                if token.type == INDENT:
                    text += token.string
                elif (token.type == OP and token.string == '.' and prev and
                      prev.type == NAME):
                    add_token(token, ' ')
                elif token.type == NAME and token.string not in kwlist:
                    if prev and prev.type == OP and prev.string == '.':
                        add_token(token, ' ')
                    else:
                        add_token(token, '+')
        except TokenError as e:
            logger.debug('token error %s', e)
        if prev and prev.type == OP and prev.string == '.':
            # Cut superfluous dot from the end of line
            text = text[:-1]
        return text

    @staticmethod
    @debug_time
    def _make_ast(code):
        """Return AST for code."""
        return ast.parse(code)

    @staticmethod
    @debug_time
    def _make_symtable(code):
        """Return symtable for code."""
        return symtable.symtable(code, '?', 'exec')

    @staticmethod
    def _minor_change(old_lines, new_lines):
        """Determine whether a minor change between old and new lines occurred.
        Return (`minor_change`, `change_lineno`) where `minor_change` is True
        when at most one change occurred and `change_lineno` is the line number
        of the change. 

        A minor change is a change in a single line while the total number of
        lines doesn't change.
        """
        if len(old_lines) != len(new_lines):
            # A different number of lines doesn't count as minor change
            return (False, None)
        old_iter = iter(old_lines)
        new_iter = iter(new_lines)
        diff_lineno = None
        lineno = 0
        try:
            while True:
                old_lines = next(old_iter)
                new_lines = next(new_iter)
                if old_lines != new_lines:
                    if diff_lineno is not None:
                        # More than one change must have happened
                        return (False, None)
                    diff_lineno = lineno
                lineno += 1
        except StopIteration:
            # We iterated through all lines with at most one change
            return (True, diff_lineno)

    @staticmethod
    @debug_time
    def _diff(old_nodes, new_nodes):
        """Return difference between iterables of nodes old_nodes and new_nodes
        as three lists of nodes to add, remove and keep.
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

    # pylint: disable=method-hidden
    def same_nodes(self, cur_node, mark_original=True, use_target=True):
        """Return nodes with the same scope as cur_node.

        The same scope is to be understood as all nodes with the same base
        symtable. In some cases this can be ambiguous.
        """
        # TODO Make this an option
        if use_target:
            target = cur_node.target
            if target is not None:
                cur_node = target
        cur_name = cur_node.name
        base_table = cur_node.base_table()
        for node in self._nodes:
            if node.name != cur_name:
                continue
            if not mark_original and node is cur_node:
                continue
            if node.base_table() == base_table:
                yield node

    def _same_nodes_cursor(self, cursor, mark_original=True):
        """Return nodes with the same scope as node at the cursor position."""
        cur_node = self.node_at(cursor)
        if cur_node is None:
            return []
        return self.same_nodes(cur_node, mark_original)

    def locations(self, types):
        visitor = _LocationCollectionVisitor(types)
        # TODO Parsing the AST for every location determination is expensive
        ast_root = ast.parse('\n'.join(self.lines))
        visitor.visit(ast_root)
        return visitor.locations


class _LocationCollectionVisitor(ast.NodeVisitor):
    """Node vistor which collects the locations of all AST nodes of a given
    type."""
    def __init__(self, types):
        self._types = types
        self.locations = []

    def visit(self, node):
        if type(node) in self._types: # pylint: disable=unidiomatic-typecheck
            self.locations.append((node.lineno, node.col_offset))
        return self.generic_visit(node)
