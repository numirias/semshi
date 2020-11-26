import ast
from collections import deque
from collections.abc import Iterable
from functools import singledispatch
from keyword import kwlist
import symtable
from token import NAME, INDENT, OP
from tokenize import TokenError, tokenize

from .util import debug_time, logger, lines_to_code, code_to_lines
from .visitor import visitor


class UnparsableError(Exception):

    def __init__(self, error):
        super().__init__()
        self.error = error


class Parser:
    """The parser parses Python code and generates source code nodes. For every
    run of `parse()` on changed source code, it returns the nodes that have
    been added and removed.
    """
    def __init__(self, exclude=None, fix_syntax=True):
        self._excluded = exclude or []
        self._fix_syntax = fix_syntax
        self._locations = {}
        self._nodes = []
        self.lines = []
        # Incremented after every parse call
        self.tick = 0
        # Holds the error of the current and previous run, so the buffer
        # handler knows if error signs need to be updated.
        self.syntax_errors = deque([None, None], maxlen=2)
        self.same_nodes = singledispatch(self.same_nodes)
        self.same_nodes.register(Iterable, self._same_nodes_cursor)

    @debug_time
    def parse(self, *args, **kwargs):
        """Wrapper for `_parse()`.

        Raises UnparsableError() if an unrecoverable error occurred.
        """
        try:
            return self._parse(*args, **kwargs)
        except (SyntaxError, RecursionError) as e:
            logger.debug('parsing error: %s', e)
            raise UnparsableError(e) from e
        finally:
            self.tick += 1

    @debug_time
    def _filter_excluded(self, nodes):
        return [n for n in nodes if n.hl_group not in self._excluded]

    def _parse(self, code, force=False):
        """Parse code and return tuple (`add`, `remove`) of added and removed
        nodes since last run. With `force`, all highlights are refreshed, even
        those that didn't change.
        """
        self._locations.clear()
        old_lines = self.lines
        new_lines = code_to_lines(code)
        minor_change, change_lineno = self._minor_change(old_lines, new_lines)
        old_nodes = self._nodes
        new_nodes = self._make_nodes(code, new_lines, change_lineno)
        # Detecting minor changes keeps us from updating a lot of highlights
        # while the user is only editing a single line.
        if minor_change and not force:
            add, rem, keep = self._diff(old_nodes, new_nodes)
            self._nodes = keep + add
        else:
            add, rem = new_nodes, old_nodes
            self._nodes = add
        # Only assign new lines when nodes have been updated accordingly
        self.lines = new_lines
        logger.debug('[%d] nodes: +%d,  -%d', self.tick, len(add), len(rem))
        return (self._filter_excluded(add), self._filter_excluded(rem))

    def _make_nodes(self, code, lines=None, change_lineno=None):
        """Return nodes in code.

        Runs AST visitor on code and produces nodes. We're passing both code
        *and* lines around to avoid lots of conversions.
        """
        if lines is None:
            lines = code_to_lines(code)
        try:
            ast_root, fixed_code, fixed_lines, error = \
                self._fix_syntax_and_make_ast(code, lines, change_lineno)
        except SyntaxError as e:
            # Apparently, fixing syntax errors failed
            self.syntax_errors.append(e)
            raise
        if fixed_code is not None:
            code = fixed_code
            lines = fixed_lines
        try:
            symtable_root = self._make_symtable(code)
        except SyntaxError as e:
            # In some cases, the symtable() call raises a syntax error which
            # hasn't been raised earlier (such as duplicate arguments)
            self.syntax_errors.append(e)
            raise
        self.syntax_errors.append(error)
        return visitor(lines, symtable_root, ast_root)

    @debug_time
    def _fix_syntax_and_make_ast(self, code, lines, change_lineno):
        """Try to fix syntax errors in code (if present) and return AST, fixed
        code and list of fixed lines of code.

        Current strategy to fix syntax errors:
        - Try to build AST from original code.
        - If that fails, call _fix_line() on the line indicated by the
          SyntaxError exception and try to build AST again.
        - If that fails, do the same with the line of the last change.
        - If all attempts failed, raise original SyntaxError exception.
        """
        # TODO Cache previous attempt?
        try:
            return self._make_ast(code), None, None, None
        except SyntaxError as e:
            orig_error = e
            error_idx = e.lineno - 1
        if not self._fix_syntax:
            # Don't even attempt to fix syntax errors.
            raise orig_error
        new_lines = lines[:]
        # Save original line to restore later
        orig_line = new_lines[error_idx]
        new_lines[error_idx] = self._fix_line(orig_line)
        new_code = lines_to_code(new_lines)
        try:
            ast_root = self._make_ast(new_code)
        except SyntaxError as exc:
            # Restore original line
            new_lines[error_idx] = orig_line
            # Fixing the line of the syntax error failed, so try again with the
            # line of last change.
            if change_lineno is None or change_lineno == error_idx:
                # Don't try to fix the changed line if it's unknown or the same
                # as the one we tried to fix before.
                raise orig_error from exc
            new_lines[change_lineno] = self._fix_line(new_lines[change_lineno])
            new_code = lines_to_code(new_lines)
            try:
                ast_root = self._make_ast(new_code)
            except SyntaxError:
                # All fixing attempts failed, so raise original syntax error.
                raise orig_error from exc
        return ast_root, new_code, new_lines, orig_error

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

    def _same_nodes_cursor(self, cursor, mark_original=True, use_target=True):
        """Return nodes with the same scope as node at the cursor position."""
        cur_node = self.node_at(cursor)
        if cur_node is None:
            return []
        return self.same_nodes(cur_node, mark_original, use_target)

    def locations_by_node_types(self, types):
        """Return locations of all AST nodes in code whose type is contained in
        `types`."""
        types_set = frozenset(types)
        try:
            return self._locations[types_set]
        except KeyError:
            pass
        visitor = _LocationCollectionVisitor(types)
        try:
            ast_ = ast.parse(lines_to_code(self.lines))
        except SyntaxError:
            return []
        visitor.visit(ast_)
        locations = visitor.locations
        self._locations[types_set] = locations
        return locations

    def locations_by_hl_group(self, group):
        """Return locations of all nodes whose highlight group is `group`."""
        return [n.pos for n in self._nodes if n.hl_group == group]


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
