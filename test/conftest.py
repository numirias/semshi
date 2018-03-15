import ast
from textwrap import dedent

from semshi.parser import Parser

from  .astpretty import pprint

def make_tree(names):
    root = {}
    for node in names:
        n = root
        prev = None
        for scope in node.env:
            name = scope.get_name()
            if name not in n:
                n[name] = {}
            prev = n
            n = n[name]
        if 'names' not in n:
            n['names'] = []
        n['names'].append(node.symname)
    return root['top']

def dump_dict(root):
    import json
    print(json.dumps(root, indent=4))


def dump_symtable(table_or_code):
    import symtable
    if isinstance(table_or_code, str):
        table = symtable.symtable(dedent(table_or_code), '?', 'exec')
    else:
        table = table_or_code
    def visit_table(table, indent=0):
        it = indent*' '
        print(it, table)
        if isinstance(table, symtable.Class):
            print(table.get_methods())
        for symbol in table.get_symbols():
            print((indent+4)*' ', symbol, symbol.is_namespace(), symbol.get_namespaces(), symbol.is_free(), symbol.is_local(), symbol.is_global())
        for child in table.get_children():
            visit_table(child, indent=indent+4)
    visit_table(table)


def dump_ast(node_or_code):
    if isinstance(node_or_code, str):
        node = ast.parse(dedent(node_or_code))
    else:
        node = node_or_code
    pprint(node)
    # tree = ast.dump(node)
    # print(tree)


def parse(code):
    # pprint(ast.parse(dedent(code)))
    add, remove = Parser().parse(dedent(code))
    assert len(remove) == 0
    for node in add:
        node.base_table()
    return add


def make_parser(code):
    parser = Parser()
    add, remove = parser.parse(dedent(code))
    return parser
