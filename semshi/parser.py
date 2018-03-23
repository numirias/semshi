import ast
from ast import ClassDef, AsyncFunctionDef, FunctionDef, Lambda, Module, ListComp, DictComp, SetComp, comprehension, Attribute, Name, GeneratorExp, AST, arg, Global, arguments, Import, ImportFrom, Try, NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq, LtE, GtE
import symtable
from .node import Node
import io
import tokenize
from token import tok_name
import itertools

from .util import logger, debug_time


BLOCKS = (Module, FunctionDef, AsyncFunctionDef, ClassDef, ListComp, DictComp, SetComp, GeneratorExp, Lambda)


class UnparsableError(Exception):

    def __init__(self, error):
        super().__init__()
        self.error = error


class Parser:

    def __init__(self, exclude=[]):
        self.exclude = exclude
        self.active_names = []
        self.active_lines = []

    @debug_time('parse')
    def parse(self, code):
        try:
            return self._parse(code)
        except RecursionError as e:
            logger.debug('recursion error')
            raise UnparsableError(e)
        except SyntaxError as e:
            logger.debug('syntax error: %s', e)
            raise UnparsableError(e)

    def _parse(self, code):
        lines = code.split('\n')

        new_names = self.make_nodes(code, lines)
        old_names = self.active_names

        # TODO
        # new_names = [n for n in new_names if n.hl_group not in self.exclude]
        # old_names = [n for n in old_names if n.hl_group not in self.exclude]

        old = self.active_lines
        new = lines

        if len(old) == 0:
            # logger.debug('no old lines -> parse all')
            names = new_names, old_names, []
        elif len(old) == len(new):
            if self.single_change(old, new):
                logger.debug('single change')
                names = self.diff(old_names, new_names)
            else:
                logger.debug('same length, but multiple changes')
                names = new_names, old_names, []
        else:
            logger.debug('mutiple insertions -> parse all')
            names = new_names, old_names, []

        added_names, removed_names, kept_names = names # TODO do we need kept names anymore?

        self.active_names = kept_names + added_names
        self.active_lines = lines
        # logger.debug('+ %d names, - %d names', len(added_names), len(removed_names))
        return (added_names, removed_names)

    def make_nodes(self, code, lines):
        ast_root = self.make_ast(code)
        st_root = self.make_symtable(code)
        visitor = Visitor(lines, st_root, ast_root)
        visitor()
        return visitor.names

    @debug_time('ast')
    def make_ast(self, code):
        return ast.parse(code)

    @debug_time('symtable')
    def make_symtable(self, code):
        return symtable.symtable(code, '?', 'exec')

    @staticmethod
    def single_change(old, new):
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
    @debug_time('diff')
    def diff(old_names, new_names):

        # TODO is sorting actually required? (we can check by comparing) for both?
        new_names = sorted(new_names)
        old_names = sorted(old_names) # TODO don't sort
        add_iter = iter(new_names)
        rem_iter = iter(old_names)

        # # logger.debug('candidates: + %d - %d', len(added), len(removed))
        # # print('adding', added)
        # # print('removing', removed)

        removed_names = []
        kept_names = []
        added_names = []
        try:
            add = rem = None
            while True:
                if add == rem:
                    if add is not None:
                        # kept_names.append(rem)
                        # rem.env = add.env
                        kept_names.append(add)
                        # A new node which is stored needs adopt the highlight
                        # ID of currently highlighted node
                        add.id = rem.id
                    add = rem = None
                    add = next(add_iter)
                    rem = next(rem_iter)
                elif add < rem:
                    added_names.append(add)
                    add = None
                    add = next(add_iter)
                elif rem < add:
                    removed_names.append(rem)
                    rem = None
                    rem = next(rem_iter)
        except StopIteration:
            if add is not None:
                added_names.append(add)
            if rem is not None:
                removed_names.append(rem)
            added_names += list(add_iter)
            removed_names += list(rem_iter)
        return added_names, removed_names, kept_names

    def node_at(self, cursor):
        lineno, col = cursor
        for node in self.active_names:
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
        for node in self.active_names:
            if ref:
                if ref == getattr(node, 'ref', None):
                    yield node
                continue
            if node.name != current_name:
                continue
            if node.base_table() == base_table:
                yield node


class Visitor:

    def __init__(self, lines, root_table, root_node):
        self.table_stack = [root_table]
        self.root_node = root_node
        self.current_env = []
        self.names = []
        self.outside = False
        self.lines = lines

    @debug_time('visitor')
    def __call__(self):
        self.visit(self.root_node)

    def new_name(self, node):
        target = node.__dict__.get('self_target')
        self.names.append(Node(node.id, node.lineno, node.col_offset, self.current_env_copy, None, target))

    def visit(self, node):
        inst = type(node)

        if inst is Name:
            # logger.debug('got self %s', getattr(node, 'self_target', None))
            self.new_name(node)
            return

        elif inst is Attribute:
            self.add_attribute(node)
            self.visit(node.value)
            return

        elif inst in (NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq, LtE, GtE):
            return

        elif inst is Try:
            self.visit_try(node)

        elif inst in (Import, ImportFrom):
            self.visit_import(node)

        elif inst is arg:
            self.visit_arg(node)

        if inst in (AsyncFunctionDef, FunctionDef, Lambda):
            # By visiting the arguments first, we maintain the symtable order
            for a in node.args.defaults + node.args.kw_defaults:
                self.visit(a)
            del node.args.defaults
            del node.args.kw_defaults

        if inst in (AsyncFunctionDef, FunctionDef):
            self.visit_function_args(node)

        if inst is ClassDef:
            for base in node.bases:
                self.visit(base)
            del node.bases
            for keyword in node.keywords:
                self.visit(keyword)
            del node.keywords

        if inst in (AsyncFunctionDef, ClassDef, FunctionDef):
            self.visit_class_function_block(node)

        if inst in (DictComp, SetComp, ListComp, GeneratorExp):
            self.visit_comp(node)

        if inst in BLOCKS:
            self.visit_block(node)
        else:
            self.iter_node(node)

    def visit_arg(self, node):
        self.names.append(Node(node.arg, node.lineno, node.col_offset, self.current_env_copy))

    def visit_block(self, node):
        t = self.table_stack.pop()
        self.table_stack += reversed(t.get_children())
        self.current_env.append(t)
        self.current_env_copy = self.current_env[:]
        self.iter_node(node)
        self.current_env.pop()
        self.current_env_copy = self.current_env[:]

    def visit_try(self, node):
        for child in node.body:
            self.visit(child)
        del node.body
        for child in node.orelse:
            self.visit(child)
        del node.orelse
        # node.

    def visit_comp(self, node):
        self.visit(node.generators[0].iter)
        node.generators[0].iter
        del node.generators[0].iter

    def visit_function_args(self, node):
        node_args = node.args
        for a in node_args.args + node_args.kwonlyargs + [node_args.vararg, node_args.kwarg]:
            if a is None:
                continue
            self.visit(a.annotation)
            del a.annotation
        self.visit(node.returns)
        del node.returns
        self.mark_self(node)

    def visit_import(self, node):
        first_line = bytes(node.col_offset * ' ' + self.lines[node.lineno-1][node.col_offset:], 'utf-8')
        other_lines = (bytes(self.lines[i] + '\n', 'utf-8') for i in itertools.count(node.lineno))
        lines = itertools.chain([first_line], other_lines)
        # print('first line', repr(first_line))
        x = tokenize.tokenize(lines.__next__)
        for token in x:
            # print(token)
            if token.type == 1 and token.string == 'import':
                break
        remaining = len(node.names)
        for alias in node.names:
            remaining -= 1
            if alias.name == '*':
                # TODO Handle star import
                continue

            for token in x:
                # print(token)
                if token.type == 1:
                    # print('found', token.string)
                    break
            if alias.asname is None:
                # print('found', token.string)
                pass
            else:
                # print('asname')
                for token in x:
                    # print(token)
                    if token.string == 'as':
                        break
                for token in x:
                    # print(token)
                    if token.type == 1:
                        break
                # print('found', token.string)

            id = token.string
            lineno = token.start[0] + node.lineno - 1
            col_offset = token.start[1]
            self.names.append(Node(id, lineno, col_offset, self.current_env_copy))

            if remaining > 0:
                for token in x:
                    if token.type == 53 and token.string == ',':
                        break
        # print()

    def visit_class_function_block(self, node):
        for x in node.decorator_list:
            self.visit(x)


        offset = 6 if type(node) is ClassDef else 4
        line_idx = node.lineno - 1
        line = self.lines[line_idx]
        start = node.col_offset + offset
        # print('starting at', line[node.col_offset])
        if not node.decorator_list and line[start:start + len(node.name)] == node.name:
            lineno = node.lineno
            col_offset = start
        else:
            lines = (bytes(self.lines[i] + '\n', 'utf-8') for i in itertools.count(node.lineno-1))
            x = tokenize.tokenize(lines.__next__)
            for token in x:
                # print(token)
                if token.type == 1 and token.string in ['class', 'def']:
                    break
            for token in x:
                if token.type == 1:
                    break

            line, col = token.start
            lineno = line + node.lineno - 1
            col_offset = col

        del node.decorator_list

        self.names.append(Node(node.name, lineno, col_offset, self.current_env_copy))

    def mark_self(self, function_node):
        # The first argument...
        try:
            arg = function_node.args.args[0]
        except IndexError:
            return
        # ...with a special name...
        if arg.arg not in ['self', 'cls']:
            return
        # ...and a class as parent scope is a self_param.
        if not isinstance(self.current_env[-1], symtable.Class):
            return
        # Let the table for the current function remember if one if the
        # parameters is a "self" parameter
        self.table_stack[-1].self_param = arg.arg

    def add_attribute(self, node):
        # TODO this doesn't check if we're inside a class
        # TODO Maybe speed up by check if node.value.id in [self, cls]
        # Only attributes of names matter. (foo.attr, but not [].attr)
        if type(node.value) is not Name:
            return
        # if node.value.id not in ['self', 'cls']:
        #     return
        if node.value.id != getattr(self.current_env[-1], 'self_param', None):
            return
        id = node.attr
        col_offset = node.value.col_offset + len(node.value.id) + 1
        lineno = node.value.lineno
        new_node = Node(node.attr, lineno, col_offset, self.current_env[:-1], is_attr=True)

        node.value.self_target = new_node # TODO
        # logger.debug('setting self_target %s %s', node.value, node.value.id)

        self.names.append(new_node)

    def iter_node(self, node):
        if node is None:
            return
        for field in node._fields:
            try:
                value = node.__dict__.get(field)
            except AttributeError:
                continue
            value_type = type(value)
            if value_type is list:
                for item in value:
                    if type(item) == str:
                        continue
                    self.visit(item)
            # elif isinstance(value, AST):
            elif value_type not in (str, int, bytes):
                self.visit(value)
