from ast import ClassDef, AsyncFunctionDef, FunctionDef, Lambda, Module, ListComp, DictComp, SetComp, comprehension, Attribute, Name, GeneratorExp, AST, arg, Global, arguments, Import, ImportFrom, Try, NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq, LtE, GtE
import io
import tokenize
from token import tok_name, NAME, OP
from itertools import count, chain

from .node import Node
from .util import logger, debug_time

# Node types which introduce a new scope
BLOCKS = (Module, FunctionDef, AsyncFunctionDef, ClassDef, ListComp, DictComp,
          SetComp, GeneratorExp, Lambda)


def advance(tokens, s=None, type=NAME):
    if s is None:
        return next(t for t in tokens if t.type == type)
    return next(t for t in tokens if t.type == type and t.string == s)


class Visitor:

    def __init__(self, lines, root_table, root_node):
        self.table_stack = [root_table]
        self.root_node = root_node
        self.env = []
        self.names = []
        self.outside = False
        self.lines = lines
        self._cur_env = None

    @debug_time('visitor')
    def __call__(self):
        self._visit(self.root_node)

    def _visit(self, node):
        """Recursively visit the node to build a list of names in their scopes.

        In some contexts, nodes appear in a different order than the scopes are
        nested. In that case attributes of a node might be visitied before
        creating a new scope and deleted afterwards so they are not revisited
        later.
        """
        # type() is fine here and a lot faster than the idiomatic isinstance()
        type_ = type(node)
        if type_ is Name:
            self.new_name(node)
            return
        elif type_ is Attribute:
            self.add_attribute(node)
            self._visit(node.value)
            return
        elif type_ in (NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq,
                       LtE, GtE):
            return
        elif type_ is Try:
            self.visit_try(node)
        elif type_ in (Import, ImportFrom):
            self.visit_import(node)
        elif type_ is arg:
            self.visit_arg(node)
        elif type_ in (AsyncFunctionDef, FunctionDef, Lambda):
            # By visiting the arguments first, we maintain the symtable order
            for arg_ in node.args.defaults + node.args.kw_defaults:
                self._visit(arg_)
            del node.args.defaults
            del node.args.kw_defaults
        elif type_ in (DictComp, SetComp, ListComp, GeneratorExp):
            self.visit_comp(node)
        elif type_ is ClassDef:
            for base in node.bases:
                self._visit(base)
            del node.bases
            for keyword in node.keywords:
                self._visit(keyword)
            del node.keywords
        if type_ in (AsyncFunctionDef, FunctionDef):
            self.visit_function_args(node)
        if type_ in (AsyncFunctionDef, ClassDef, FunctionDef):
            self.visit_class_function_block(node)
        if type_ in BLOCKS:
            self._visit_block(node)
        else:
            self._iter_node(node)

    def new_name(self, node):
        # Using __dict__.get() is faster than getattr()
        target = node.__dict__.get('self_target')
        self.names.append(Node(node.id, node.lineno, node.col_offset, self._cur_env, None, target))

    def visit_arg(self, node):
        self.names.append(Node(node.arg, node.lineno, node.col_offset, self._cur_env))

    def _visit_block(self, node):
        current_table = self.table_stack.pop()
        self.table_stack += reversed(current_table.get_children())
        self.env.append(current_table)
        self._cur_env = self.env[:]
        self._iter_node(node)
        self.env.pop()
        self._cur_env = self.env[:]

    def visit_try(self, node):
        """Visit try-except."""
        for child in node.body:
            self._visit(child)
        del node.body
        for child in node.orelse:
            self._visit(child)
        del node.orelse

    def visit_comp(self, node):
        self._visit(node.generators[0].iter)
        node.generators[0].iter
        del node.generators[0].iter

    def visit_function_args(self, node):
        node_args = node.args
        for arg in node_args.args + node_args.kwonlyargs + [node_args.vararg, node_args.kwarg]:
            if arg is None:
                continue
            self._visit(arg.annotation)
            del arg.annotation
        self._visit(node.returns)
        del node.returns
        self.mark_self(node)

    @debug_time
    def visit_import(self, node):
        """Visit import statement.

        Unlike other nodes in the AST, names in import statements don't come
        with a specified line number and column. Therefore, we need to use the
        tokenizer on that part of the code to get the exact position. Since
        using the tokenize module is slow, we only use it where absoultely
        necessary.
        """
        import time
        t = time.time()
        first_line = bytes(node.col_offset * ' ' + self.lines[node.lineno-1][node.col_offset:], 'utf-8')
        other_lines = (bytes(self.lines[i] + '\n', 'utf-8') for i in count(node.lineno))
        lines = chain([first_line], other_lines)
        tokens = tokenize.tokenize(lines.__next__)
        # Advance to "import" keyword
        advance(tokens, 'import')
        for alias, remaining in zip(node.names, count(len(node.names)-1, -1)):
            if alias.name == '*':
                continue # TODO Handle star import
            # If it's an "as" alias import...
            if alias.asname is not None:
                # ...advance to "as" keyword.
                advance(tokens, 'as')
            token = advance(tokens)
            self.names.append(Node(
                token.string,
                token.start[0] + node.lineno - 1,
                token.start[1],
                self._cur_env,
            ))
            # If there are more imports in that import statement...
            if remaining:
                # ...they must be comma-separated, so advance to next comma.
                advance(tokens, ',', OP)
        logger.debug('%f', time.time() - t)
        logger.debug('%d', node.lineno)

    def visit_class_function_block(self, node):
        """Visit class or function definition.

        The AST does not include the line and column of the names of class and
        function definitions, so we need to determine it using tokenize.
        """
        for decorator in node.decorator_list:
            self._visit(decorator)
        # Offset is the length of the keyword
        offset = 6 if type(node) is ClassDef else 4
        line = self.lines[node.lineno - 1]
        start = node.col_offset + offset
        if not node.decorator_list and line[start:start+len(node.name)] == node.name:
            lineno = node.lineno
            col_offset = start
        else:
            lines = (bytes(self.lines[i] + '\n', 'utf-8') for i in count(node.lineno-1))
            tokens = tokenize.tokenize(lines.__next__)
            for token in tokens:
                if token.type == 1 and token.string in ['class', 'def']:
                    break
            token = advance(tokens)

            line, col = token.start
            lineno = line + node.lineno - 1
            col_offset = col
        del node.decorator_list
        self.names.append(Node(node.name, lineno, col_offset, self._cur_env))

    def mark_self(self, function_node):
        """Mark self argument if present.

        Determine if an argument is a self argument and add a reference in the
        function's symtable.
        """
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
        # Let the table for the current function scope remember if one if the
        # parameters is a "self" parameter
        self.table_stack[-1].self_param = arg.arg

    def add_attribute(self, node):
        """Add node as an attribute."""
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

    def _iter_node(self, node):
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
                    self._visit(item)
            # elif isinstance(value, AST):
            elif value_type not in (str, int, bytes):
                self._visit(value)
