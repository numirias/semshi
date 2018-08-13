# pylint: disable=unidiomatic-typecheck
from ast import (AsyncFunctionDef, Attribute, ClassDef, DictComp, Eq,
                 ExceptHandler, FunctionDef, GeneratorExp, Global, Gt, GtE,
                 Import, ImportFrom, Lambda, ListComp, Load, Lt, LtE, Module,
                 Name, NameConstant, Nonlocal, NotEq, Num, SetComp, Store, Str,
                 Try, arg)
from itertools import count
from token import NAME, OP
from tokenize import tokenize

from .node import ATTRIBUTE, IMPORTED, PARAMETER_UNUSED, SELF, Node
from .util import debug_time


# Node types which introduce a new scope
BLOCKS = (Module, FunctionDef, AsyncFunctionDef, ClassDef, ListComp, DictComp,
          SetComp, GeneratorExp, Lambda)
FUNCTION_BLOCKS = (FunctionDef, Lambda, AsyncFunctionDef)
# Node types which don't require any action
SKIP = (NameConstant, Str, Num, Store, Load, Eq, Lt, Gt, NotEq, LtE, GtE)


def tokenize_lines(lines):
    return tokenize(((line + '\n').encode('utf-8') for line in lines).__next__)


def advance(tokens, s=None, type=NAME):
    """Advance token stream `tokens`.

    Advances to next token of type `type` with the string representation `s` or
    matching one of the strings in `s` if `s` is an iterable. Without any
    arguments, just advances to next NAME token.
    """
    if s is None:
        cond = lambda token: True
    elif isinstance(s, str):
        cond = lambda token: token.string == s
    else:
        cond = lambda token: token.string in s
    return next(t for t in tokens if t.type == type and cond(t))


@debug_time
def visitor(lines, symtable_root, ast_root):
    visitor = Visitor(lines, symtable_root)
    visitor.visit(ast_root)
    return visitor.nodes


class Visitor:
    """The visitor visits the AST recursively to extract relevant name nodes in
    their context.
    """

    def __init__(self, lines, root_table):
        self._lines = lines
        self._table_stack = [root_table]
        self._env = []
        # Holds a copy of the current environment to avoid repeated copying
        self._cur_env = None
        self.nodes = []

    def visit(self, node):
        """Recursively visit the node to build a list of names in their scopes.

        In some contexts, nodes appear in a different order than the scopes are
        nested. In that case, attributes of a node might be visitied before
        creating a new scope and deleted afterwards so they are not revisited
        later.
        """
        # Use type() because it's faster than the more idiomatic isinstance()
        type_ = type(node)
        if type_ is Name:
            self._new_name(node)
            return
        if type_ is Attribute:
            self._add_attribute(node)
            self.visit(node.value)
            return
        if type_ in SKIP:
            return
        if type_ is Try:
            self._visit_try(node)
        elif type_ is ExceptHandler:
            self._visit_except(node)
        elif type_ in (Import, ImportFrom):
            self._visit_import(node)
        elif type_ is arg:
            self._visit_arg(node)
        elif type_ in FUNCTION_BLOCKS:
            self._visit_arg_defaults(node)
        elif type_ in (ListComp, SetComp, DictComp, GeneratorExp):
            self._visit_comp(node)
        elif type_ in (Global, Nonlocal):
            keyword = 'global' if type_ is Global else 'nonlocal'
            self._visit_global_nonlocal(node, keyword)
        if type_ in (FunctionDef, ClassDef, AsyncFunctionDef):
            self._visit_class_function_definition(node)
            if type_ is ClassDef:
                self._visit_class_meta(node)
            else:
                self._visit_args(node)
                self._mark_self(node)
        # Either make a new block scope...
        if type_ in BLOCKS:
            current_table = self._table_stack.pop()
            self._table_stack += reversed(current_table.get_children())
            self._env.append(current_table)
            self._cur_env = self._env[:]
            if type_ in FUNCTION_BLOCKS:
                current_table.unused_params = {}
                self._iter_node(node)
                # Set the hl group of all parameters that didn't appear in the
                # function body to "unused parameter".
                for param in current_table.unused_params.values():
                    if param.hl_group == SELF:
                        # SELF args should never be shown as unused
                        continue
                    param.hl_group = PARAMETER_UNUSED
                    param.update_tup()
            else:
                self._iter_node(node)
            self._env.pop()
            self._cur_env = self._env[:]
        # ...or just iterate through the node's attributes.
        else:
            self._iter_node(node)

    def _new_name(self, node):
        self.nodes.append(Node(
            node.id,
            node.lineno,
            node.col_offset,
            self._cur_env,
            # Using __dict__.get() is faster than getattr()
            node.__dict__.get('_target'),
        ))

    def _visit_arg(self, node):
        """Visit function argument."""
        node = Node(node.arg, node.lineno, node.col_offset, self._cur_env)
        self.nodes.append(node)
        # Register as unused parameter for now. The entry is removed if it's
        # found to be used later.
        self._env[-1].unused_params[node.name] = node

    def _visit_arg_defaults(self, node):
        """Visit argument default values."""
        for arg_ in node.args.defaults + node.args.kw_defaults:
            self.visit(arg_)
        del node.args.defaults
        del node.args.kw_defaults

    def _visit_try(self, node):
        """Visit try-except."""
        for child in node.body:
            self.visit(child)
        del node.body
        for child in node.orelse:
            self.visit(child)
        del node.orelse

    def _visit_except(self, node):
        """Visit except branch."""
        if node.name is None:
            # There is no "as ..." branch, so don't do anything.
            return
        # We can't really predict the line for "except-as", so we must always
        # tokenize.
        line_idx = node.lineno - 1
        tokens = tokenize_lines(self._lines[i] for i in count(line_idx))
        advance(tokens, 'as')
        token = advance(tokens)
        lineno = token.start[0] + line_idx
        cur_line = self._lines[lineno - 1]
        self.nodes.append(Node(
            node.name,
            lineno,
            len(cur_line[:token.start[1]].encode('utf-8')),
            self._cur_env,
        ))

    def _visit_comp(self, node):
        """Visit set/dict/list comprehension or generator expression."""
        generator = node.generators[0]
        self.visit(generator.iter)
        del generator.iter

    def _visit_class_meta(self, node):
        """Visit class bases and keywords."""
        for base in node.bases:
            self.visit(base)
        del node.bases
        for keyword in node.keywords:
            self.visit(keyword)
        del node.keywords

    def _visit_args(self, node):
        """Visit function arguments."""
        args = node.args
        for arg in args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
            if arg is None:
                continue
            self.visit(arg.annotation)
            del arg.annotation
        self.visit(node.returns)
        del node.returns

    def _visit_import(self, node):
        """Visit import statement.

        Unlike other nodes in the AST, names in import statements don't come
        with a specified line number and column. Therefore, we need to use the
        tokenizer on that part of the code to get the exact position. Since
        using the tokenize module is slow, we only use it where absolutely
        necessary.
        """
        line_idx = node.lineno - 1
        # We first try to guess the import line to avoid having to use the
        # tokenizer. This will fail in some cases as we just cover the most
        # common import syntax.
        name = node.names[0].name
        asname = node.names[0].asname
        target = asname or name
        if target != '*' and '.' not in target:
            guess = 'import ' + name + (' as ' + asname if asname else '')
            if type(node) == ImportFrom:
                guess = 'from ' + (node.module or node.level * '.') + ' ' + \
                        guess
            if self._lines[line_idx] == guess:
                self.nodes.append(Node(
                    target,
                    node.lineno,
                    len(guess.encode('utf-8')) - len(target.encode('utf-8')),
                    self._cur_env,
                    None,
                    IMPORTED,
                ))
                return
        # Guessing the line failed, so we need to use the tokenizer
        tokens = tokenize_lines(self._lines[i] for i in count(line_idx))
        while True:
            # Advance to next "import" keyword
            token = advance(tokens, 'import')
            cur_line = self._lines[line_idx + token.start[0] - 1]
            # Determine exact byte offset. token.start[1] just holds the char
            # index which may give a wrong position.
            offset = len(cur_line[:token.start[1]].encode('utf-8'))
            # ...until we found the matching one.
            if offset >= node.col_offset:
                break
        for alias, more in zip(node.names, count(1 - len(node.names))):
            if alias.name == '*':
                continue
            # If it's an "as" alias import...
            if alias.asname is not None:
                # ...advance to "as" keyword.
                advance(tokens, 'as')
            token = advance(tokens)
            cur_line = self._lines[line_idx + token.start[0] - 1]
            self.nodes.append(Node(
                token.string,
                token.start[0] + line_idx,
                # Exact byte offset of the token
                len(cur_line[:token.start[1]].encode('utf-8')),
                self._cur_env,
                None,
                IMPORTED,
            ))
            # If there are more imports in that import statement...
            if more:
                # ...they must be comma-separated, so advance to next comma.
                advance(tokens, ',', OP)

    def _visit_class_function_definition(self, node):
        """Visit class or function definition.

        We need to use the tokenizer here for the same reason as in
        _visit_import (no line/col for names in class/function definitions).
        """
        decorators = node.decorator_list
        for decorator in decorators:
            self.visit(decorator)
        del node.decorator_list
        line_idx = node.lineno - 1
        # Guess offset of the name (length of the keyword + 1)
        start = node.col_offset + (6 if type(node) is ClassDef else 4)
        stop = start + len(node.name)
        # If the node has no decorators and its name appears directly after the
        # definition keyword, we found its position and don't need to tokenize.
        if not decorators and self._lines[line_idx][start:stop] == node.name:
            lineno = node.lineno
            column = start
        else:
            tokens = tokenize_lines(self._lines[i] for i in count(line_idx))
            advance(tokens, ('class', 'def'))
            token = advance(tokens)
            lineno = token.start[0] + line_idx
            column = token.start[1]
        self.nodes.append(Node(node.name, lineno, column, self._cur_env))

    def _visit_global_nonlocal(self, node, keyword):
        line_idx = node.lineno - 1
        line = self._lines[line_idx]
        indent = line[:-len(line.lstrip())]
        if line == indent + keyword + ' ' + ', '.join(node.names):
            offset = len(indent) + len(keyword) + 1
            for name in node.names:
                self.nodes.append(Node(
                    name,
                    node.lineno,
                    offset,
                    self._cur_env,
                ))
                # Add 2 bytes for the comma and space
                offset += len(name.encode('utf-8')) + 2
            return
        # Couldn't guess line, so we need to tokenize.
        tokens = tokenize_lines(self._lines[i] for i in count(line_idx))
        # Advance to global/nonlocal statement
        advance(tokens, keyword)
        for name, more in zip(node.names, count(1 - len(node.names))):
            token = advance(tokens)
            cur_line = self._lines[line_idx + token.start[0] - 1]
            self.nodes.append(Node(
                token.string,
                token.start[0] + line_idx,
                len(cur_line[:token.start[1]].encode('utf-8')),
                self._cur_env,
            ))
            # If there are more declared names...
            if more:
                # ...advance to next comma.
                advance(tokens, ',', OP)

    def _mark_self(self, node):
        """Mark self/cls argument if the current function has one.

        Determine if an argument is a self argument (the first argument of a
        method called "self" or "cls") and add a reference in the function's
        symtable.
        """
        # The first argument...
        try:
            arg = node.args.args[0]
        except IndexError:
            return
        # ...with a special name...
        if arg.arg not in ('self', 'cls'):
            return
        # ...and a class as parent scope is a self_param.
        if not self._env[-1].get_type() == 'class':
            return
        # Let the table for the current function scope remember the param
        self._table_stack[-1].self_param = arg.arg

    def _add_attribute(self, node):
        """Add node as an attribute.

        The only relevant attributes are attributes to self or cls in a
        method (e.g. "self._name").
        """
        # Node must be an attribute of a name (foo.attr, but not [].attr)
        if type(node.value) is not Name:
            return
        target_name = node.value.id
        # Redundant, but may spare us the getattr() call in the next step
        if target_name not in ('self', 'cls'):
            return
        # Only register attributes of self/cls parameter
        if target_name != getattr(self._env[-1], 'self_param', None):
            return
        new_node = Node(
            node.attr,
            node.value.lineno,
            node.value.col_offset + len(target_name) + 1,
            self._env[:-1],
            None, # target
            ATTRIBUTE,
        )
        node.value._target = new_node # pylint: disable=protected-access
        self.nodes.append(new_node)

    def _iter_node(self, node):
        """Iterate through fields of the node."""
        if node is None:
            return
        for field in node._fields:
            value = node.__dict__.get(field, None)
            if value is None:
                continue
            value_type = type(value)
            if value_type is list:
                for item in value:
                    if type(item) == str:
                        continue
                    self.visit(item)
            # We would want to use isinstance(value, AST) here. Not sure how
            # much more expensive that is, though.
            elif value_type not in (str, int, bytes):
                self.visit(value)
