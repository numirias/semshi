from ast import ClassDef, AsyncFunctionDef, FunctionDef, Lambda, Module, ListComp, DictComp, SetComp, comprehension, Attribute, Name, GeneratorExp, AST, arg, Global, arguments, Import, ImportFrom, Try, NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq, LtE, GtE
import io
import tokenize
from token import tok_name
import itertools

from .node import Node
from .util import logger, debug_time


BLOCKS = (Module, FunctionDef, AsyncFunctionDef, ClassDef, ListComp, DictComp,
          SetComp, GeneratorExp, Lambda)


class Visitor:

    def __init__(self, lines, root_table, root_node):
        self.table_stack = [root_table]
        self.root_node = root_node
        self.env = []
        self.names = []
        self.outside = False
        self.lines = lines

    @debug_time('visitor')
    def __call__(self):
        self.visit(self.root_node)

    def new_name(self, node):
        target = node.__dict__.get('self_target')
        self.names.append(Node(node.id, node.lineno, node.col_offset, self.current_env, None, target))

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
        self.names.append(Node(node.arg, node.lineno, node.col_offset, self.current_env))

    def visit_block(self, node):
        t = self.table_stack.pop()
        self.table_stack += reversed(t.get_children())
        self.env.append(t)
        self.current_env = self.env[:]
        self.iter_node(node)
        self.env.pop()
        self.current_env = self.env[:]

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
            self.names.append(Node(id, lineno, col_offset, self.current_env))

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

        self.names.append(Node(node.name, lineno, col_offset, self.current_env))

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
        if not self.env[-1].get_type() == 'class':
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
        if node.value.id != getattr(self.env[-1], 'self_param', None):
            return
        id = node.attr
        col_offset = node.value.col_offset + len(node.value.id) + 1
        lineno = node.value.lineno
        new_node = Node(node.attr, lineno, col_offset, self.env[:-1], is_attr=True)

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
