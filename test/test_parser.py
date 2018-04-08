import os
from textwrap import dedent
import pytest
from semshi.node import Node, group, UNRESOLVED, FREE, SELF, PARAM, BUILTIN, GLOBAL, LOCAL, IMPORTED
from semshi.parser import Parser, UnparsableError
from semshi import parser

from .conftest import parse, make_parser, make_tree, dump_dict, dump_ast, dump_symtable


# TODO Reformat multiline stirngs from """ to '''


def test_group():
    assert group('foo') == 'semshiFoo'


def test_basic():
    names = parse("""
    x = 1
    """)
    assert [n.name for n in names] == ['x']


def test_no_names():
    names = parse("""
    """)
    assert names == []
    names = parse("""
    pass
    """)
    assert names == []


def test_recursion_error():
    with pytest.raises(parser.UnparsableError):
        parse(' + '.join(1000 * ['a']))


def test_syntax_error():
    with pytest.raises(parser.UnparsableError):
        parse('foo bar')


def test_name_len():
    """Name length needs to be byte length for the correct HL offset."""
    names = parse('asd + äöü')
    assert names[0].end - names[0].col == 3
    assert names[1].end - names[1].col == 6


def test_comprehension_scopes():
    names = parse("""
    [a for b in c]
    (d for e in f)
    {g for h in i}
    {j:k for l in m}
    """)
    root = make_tree(names)
    assert root['names'] == ['c', 'f', 'i', 'm']
    assert root['listcomp']['names'] == ['a', 'b']
    assert root['genexpr']['names'] == ['d', 'e']
    assert root['setcomp']['names'] == ['g', 'h']
    assert root['dictcomp']['names'] == ['j', 'k', 'l']


def test_function_scopes():
    names = parse("""
    def func(a, b, *c, d=e, f=[g for g in h], **i):
        pass
    def func2(j=k):
        pass
    func(x, y=p, **z)
    """)
    root = make_tree(names)
    assert root['names'] == [
        'e', 'h', 'func', 'k', 'func2', 'func', 'x', 'p', 'z'
    ]
    assert root['listcomp']['names'] == ['g', 'g']
    assert root['func']['names'] == ['a', 'b', 'c', 'd', 'f', 'i']
    assert root['func2']['names'] == ['j']


def test_class_scopes():
    names = parse("""
    a = 1
    class A(x, y=z):
        a = 2
        def f():
            a
    """)
    root = make_tree(names)
    assert root['names'] == ['a', 'A', 'x', 'z']


def test_import_scopes_and_positions():
    names = parse("""
    import aa
    import BB as cc
    from DD import ee
    from FF.GG import hh
    import ii.jj
    import kk, ll
    from MM import NN as oo
    from PP import *
    import qq, RR as tt, UU as vv
    from WW import xx, YY as zz
    import aaa; import bbb
    from CCC import (ddd,
    eee)
    import FFF.GGG as hhh
    from III.JJJ import KKK as lll
    import mmm.NNN.OOO, ppp.QQQ
    """)
    root = make_tree(names)
    assert root['names'] == [
        'aa', 'cc', 'ee', 'hh', 'ii', 'kk', 'll', 'oo', 'qq', 'tt', 'vv', 'xx',
        'zz', 'aaa', 'bbb', 'ddd', 'eee', 'hhh', 'lll', 'mmm', 'ppp'
    ]
    assert [(name.name,) + name.pos for name in names] == [
        ('aa', 2, 7),
        ('cc', 3, 13),
        ('ee', 4, 15),
        ('hh', 5, 18),
        ('ii', 6, 7),
        ('kk', 7, 7),
        ('ll', 7, 11),
        ('oo', 8, 21),
        ('qq', 10, 7),
        ('tt', 10, 17),
        ('vv', 10, 27),
        ('xx', 11, 15),
        ('zz', 11, 25),
        ('aaa', 12, 7),
        ('bbb', 12, 19),
        ('ddd', 13, 17),
        ('eee', 14, 0),
        ('hhh', 15, 18),
        ('lll', 16, 27),
        ('mmm', 17, 7),
        ('ppp', 17, 20),
    ]


def test_multibyte_import_positions():
    names = parse('''
    import aaa, bbb
    import äää, ööö
    aaa; import bbb, ccc
    äää; import ööö, üüü
    import äää; import ööö, üüü; from äää import ööö; import üüü as äää
    from x import (
        äää, ööö
    )
    from foo \
            import äää
    ''')
    positions = [(n.col, n.end) for n in names]
    assert positions == [
        (7, 10), (12, 15),
        (7, 13), (15, 21),
        (0, 3), (12, 15), (17, 20),
        (0, 6), (15, 21), (23, 29),
        (7, 13), (22, 28), (30, 36), (57, 63), (82, 88),
        (4, 10), (12, 18),
        (28, 34),
    ]

def test_name_mangling():
    """Leading double underscores can lead to a different symbol name."""
    names = parse("""
    __foo = 1
    class A:
        __foo
        class B:
            __foo
            def f():
                __foo
        class __C:
            pass
    class _A:
        def f():
            __x
    class _A_:
        def f():
            __x
    class ___A_:
        def f():
            __x
    """)
    root = make_tree(names)
    assert root['names'] == ['__foo', 'A', '_A', '_A_', '___A_']
    assert root['A']['names'] == ['_A__foo', 'B', '_A__C']
    assert root['A']['B']['names'] == ['_B__foo', 'f']
    assert root['A']['B']['f']['names'] == ['_B__foo']
    assert root['_A']['f']['names'] == ['_A__x']
    assert root['_A_']['f']['names'] == ['_A___x']
    assert root['___A_']['f']['names'] == ['_A___x']


def test_self_param():
    """If self/cls appear in a class, they must have a speical group."""
    names = parse("""
    self
    def x(self):
        pass
    class Foo:
        def x(self):
            pass
            def y():
                self
            def z(self):
                self
        def a(foo, self):
            pass
        def b(foo, cls):
            pass
        def c(cls, foo):
            pass
    """)
    groups = [n.hl_group for n in names if n.name in ['self', 'cls']]
    assert groups == [
        UNRESOLVED, PARAM, SELF, FREE, PARAM, PARAM, PARAM, PARAM, SELF
    ]


def test_self_with_decorator():
    names = parse('''
    class Foo:
        @decorator(lambda k: k)
        def x(self):
            self
    ''')
    assert names[-1].hl_group == SELF


def test_self_target():
    """The target of a self with an attribute should be the attribute node."""
    parser = make_parser("""
    self.abc
    class Foo:
        def x(self):
            self.abc
    """)
    names = parser._nodes
    assert names[0].target is None
    last_self = names[-1]
    abc = names[-2]
    assert last_self.target is abc
    assert last_self.target.name == 'abc'
    assert list(parser.same_nodes(last_self)) == [abc]


def test_unresolved_name():
    names = parse("""
    def foo():
        a
    """)
    assert names[1].hl_group == UNRESOLVED

def test_imported_names():
    names = parse("""
    import foo
    import abs
    foo, abs
    """)
    assert [n.hl_group for n in names] == [IMPORTED] * 4


def test_nested_comprehension():
    names = parse("""
    [a for b in c for d in e for f in g]
    [h for i in [[x for y in z] for k in [l for m in n]]]
    [o for p, q, r in s]
    """)
    root = make_tree(names)
    assert root['names'] == ['c', 'n', 's']
    assert root['listcomp']['names'] == [
        'a', 'b', 'd', 'e', 'f', 'g', 'l', 'm', 'z', 'k', 'h', 'i', 'o', 'p',
        'q', 'r'
    ]

def test_try_except_order():
    names = parse("""
    try:
        def A():
            a
    except ImportError:
        def B():
            b
    else:
        def C():
            c
    finally:
        def D():
            d
    """)
    root = make_tree(names)
    assert root['A']['names'] == ['a']
    assert root['B']['names'] == ['b']
    assert root['C']['names'] == ['c']
    assert root['D']['names'] == ['d']


def test_lambda():
    names = parse("""
    lambda a: b
    lambda x=y: z
    """)
    root = make_tree(names)
    assert root['lambda']['names'] == ['a', 'b', 'x', 'z']
    assert root['names'] == ['y']


@pytest.mark.skipif('sys.version_info < (3, 6)')
def test_fstrings():
    assert [n.name for n in parse('f\'{foo}\'')] == ['foo']


def test_type_hints():
    names = parse("""
    def f(a:A, b, *c:C, d:D=dd, **e:E) -> z:
        pass
    async def f2(x:X=y):
        pass
    """)
    root = make_tree(names)
    assert root['names'] == [
        'dd','f', 'A', 'D', 'C', 'E', 'z', 'y', 'f2', 'X'
    ]


def test_decorator():
    names = parse("""
    @d1(a, b=c)
    class A: pass
    @d2(x, y=z)
    def B():
        pass
    @d3
    async def C():
        pass
    """)
    root = make_tree(names)
    assert root['names'] == [
        'd1', 'a', 'c', 'A', 'd2', 'x', 'z', 'B', 'd3', 'C'
    ]

def test_global_builtin():
    """A builtin name assigned globally should be highlighted as a global, not
    a builtin."""
    names = parse("""
    len
    set = 1
    def foo(): set, str
    """)
    assert names[0].hl_group == BUILTIN
    assert names[-2].hl_group == GLOBAL
    assert names[-1].hl_group == BUILTIN

def test_global_statement():
    names = parse("""
    x = 1
    def foo():
        global x
        x
    """)
    assert names[-1].hl_group == GLOBAL


def test_positions():
    names = parse("""
    a = 1
    def func(x=y):
        b = 2
    """)
    assert [(name.name,) + name.pos for name in names] == [
        ('a', 2, 0),
        ('y', 3, 11),
        ('func', 3, 4),
        ('x', 3, 9),
        ('b', 4, 4),
    ]


def test_class_and_function_positions():
    names = parse("""
    def aaa(): pass
    async def bbb(): pass
    async  def  ccc(): pass
    class ddd(): pass
    class \t\f eee(): pass
    class \\
            \\
      ggg: pass
    @deco
    @deco2
    @deco3
    class hhh():
        def foo():
            pass
    """)
    assert [name.pos for name in names] == [
        (2, 4),
        (3, 10),
        (4, 12),
        (5, 6),
        (6, 9),
        (9, 2),
        (10, 1),
        (11, 1),
        (12, 1),
        (13, 6),
        (14, 8),
    ]


def test_same_nodes():
    parser = make_parser("""
    x = 1
    class A:
        x
        def B():
            x
    """)
    names = parser._nodes
    x, A, A_x, B, B_x = names
    same_nodes = set(parser.same_nodes(x))
    assert same_nodes == {x, A_x, B_x}


def test_base_scope_global():
    parser = make_parser("""
    x = 1
    def a():
        x = 2
        def b():
            global x
            x
    """)
    names = parser._nodes
    x, a, a_x, b, b_x = names
    same_nodes = set(parser.same_nodes(x))
    assert same_nodes == {x, b_x}


def test_base_scope_free():
    parser = make_parser("""
    def a():
        x = 1
        def b():
            x
    """)
    names = parser._nodes
    a, a_x, b, b_x = names
    same_nodes = set(parser.same_nodes(a_x))
    assert same_nodes == {a_x, b_x}


def test_base_scope_class():
    parser = make_parser("""
    class A:
        x = 1
        x
    """)
    names = parser._nodes
    A, x1, x2 = names
    same_nodes = set(parser.same_nodes(x1))
    assert same_nodes == {x1, x2}


def test_base_scope_class_nested():
    parser = make_parser("""
    def z():
        x = 1
        class A():
            x = 2
            def b():
                return x
    """)
    names = parser._nodes
    z, z_x, A, A_x, b, b_x = names
    same_nodes = set(parser.same_nodes(z_x))
    assert same_nodes == {z_x, b_x}


def test_base_scope_nonlocal_free():
    parser = make_parser("""
    def foo():
        a = 1
        def bar():
            nonlocal a
            a = 1
    """)
    foo, foo_a, bar, bar_a = parser._nodes
    assert set(parser.same_nodes(foo_a)) == {foo_a, bar_a}


def test_attributes():
    parser = make_parser("""
    aa.bb
    cc.self.dd
    self.ee
    def a(self):
        self.ff
    class A:
        def b(self):
            self.gg
    class B:
        def c(self):
            self.gg
        def d(self):
            self.gg
        def e(self):
            self.hh
        def f(foo):
            self.gg
    """)
    names = parser._nodes
    names = [n for n in names if n.is_attr]
    b_gg, c_gg, d_gg, e_hh = names
    same_nodes = set(parser.same_nodes(c_gg))
    assert same_nodes == {c_gg, d_gg}


def test_same_nodes_exclude_current():
    parser = make_parser('a, a, a')
    a0, a1, a2 = parser._nodes
    assert set(parser.same_nodes(a0, mark_original=False)) == {a1, a2}


@pytest.mark.xfail
def test_refresh_names():
    """Add and clear exact names."""
    parser = Parser()
    add, clear = parser.parse(dedent("""
    def foo():
        x = y
    """))
    assert len(add) == 3
    assert len(clear) == 0
    add, clear = parser.parse(dedent("""
    def foo():
        x = y
    """))
    assert len(add) == 0
    assert len(clear) == 0
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
    """))
    assert len(add) == 1
    assert len(clear) == 1
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
        a, b
    """))
    assert len(add) == 2
    assert len(clear) == 0
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
        c, d
    """))
    assert len(add) == 2
    assert len(clear) == 2
    add, clear = parser.parse(dedent("""
    def foo():
        z = y, k
        1, 1
    """))
    assert len(add) == 1
    assert len(clear) == 2


def test_refresh_names_new():
    """Clear everything if more than one line changes."""
    parser = Parser()
    add, clear = parser.parse(dedent("""
    def foo():
        x = y
    """))
    assert len(add) == 3
    assert len(clear) == 0
    add, clear = parser.parse(dedent("""
    def foo():
        x = y
    """))
    assert len(add) == 0
    assert len(clear) == 0
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
    """))
    assert len(add) == 1
    assert len(clear) == 1
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
        a, b
    """))
    assert len(add) == 5
    assert len(clear) == 3
    add, clear = parser.parse(dedent("""
    def foo():
        z = y
        c, d
    """))
    assert len(add) == 2
    assert len(clear) == 2
    add, clear = parser.parse(dedent("""
    def foo():
        z = y, k
        1, 1
    """))
    assert len(add) == 4
    assert len(clear) == 5


@pytest.mark.xfail
def test_efficient_diff():
    # TODO Deprecated?
    from semshi.util import logger
    import time
    parser = Parser()
    code = '\n'.join(['foo' + str(d) for d in range(10000)])

    t = time.time()
    parser.parse(code)
    logger.debug('FIRST %f', time.time() - t)

    t = time.time()
    code = '\n'.join(['foo' + str(d + (d % 2)) for d in range(10000)])
    parser.parse(code)
    logger.debug('SECOND %f', time.time() - t)
    # TODO
    raise


def test_exclude_types():
    parser = Parser(exclude=[LOCAL])
    add, clear = parser.parse(dedent('''
    a = 1
    def f():
        b, c = 1
        a + b
    '''))
    assert [n.name for n in add] == ['a']
    assert clear == []
    add, clear = parser.parse(dedent('''
    a = 1
    def f():
        b, c = 1
        a + c
    '''))
    assert add == []
    assert clear == []
    add, clear = parser.parse(dedent('''
    a = 1
    def f():
        b, c = 1
        g + c
    '''))
    assert [n.name for n in add] == ['g']
    assert [n.name for n in clear] == ['a']
    add, clear = parser.parse(dedent('''
    a = 1
    def f():
        b, c = 1
        0 + c
    '''))
    assert add == []
    assert [n.name for n in clear] == ['g']


def test_exclude_types_same_nodes():
    parser = Parser(exclude=[UNRESOLVED])
    add, clear = parser.parse('a, a')
    assert len(add) == 0
    assert [n.pos for n in parser.same_nodes((1, 0))] == [(1, 0), (1, 3)]


class TestNode:

    def test_node(self):
        class Symbol:
            def __init__(self, name, **kwargs):
                self.name = name
                for k, v in kwargs.items():
                    setattr(self, 'is_' + k, lambda: v)
            def __getattr__(self, item):
                if item.startswith('is_'):
                    return lambda: False
                raise AttributeError(item)

        class Table:
            def __init__(self, symbols, type=None):
                self.symbols = symbols
                self.type = type or 'module'
            def lookup(self, name):
                return next(sym for sym in self.symbols if sym.name == name)
            def get_type(self):
                return self.type

        a = Node('foo', 0, 0, [Table([Symbol('foo', local=True)])])
        b = Node('bar', 0, 10, [Table([Symbol('bar', local=True)])])
        assert a.id + 1 == b.id


class TestDiffs:

    @pytest.mark.xfail
    def test_insertion(self):
        # TODO Deprecated.
        def insertions(c1, c2):
            return Parser.insertions(c1, c2)
        assert insertions(list('abc'), list('Xabc')) == (0, 1)
        assert insertions(list('abc'), list('aXXbc')) == (1, 2)
        assert insertions(list('abc'), list('aXbXc')) is None
        assert insertions(list(''), list('X')) == (0, 1)
        assert insertions(list('a'), list('aXX')) == (1, 2)

    def test_minor_change(self):
        def minor_change(c1, c2):
            return Parser._minor_change(c1, c2)
        assert minor_change(list('abc'), list('axc'))
        assert not minor_change(list('abc'), list('xbx'))
        assert not minor_change(list('abc'), list('abcedf'))
        assert minor_change(list('abc'), list('abc'))

    def test_diff(self):
        """The id of a saved name should remain the same so that we can remove
        it later by ID."""
        # TODO remove prints
        parser = Parser()
        add0, rem = parser.parse('foo')
        print(add0, rem)
        add, rem = parser.parse('foo ')
        print(add, rem)
        print('active', parser._nodes)
        add, rem = parser.parse('foo = 1')
        print(add, rem)
        assert add0[0].id == rem[0].id


@pytest.mark.skip
def test_multiple_files():
    """Fuzzing tests against lots of different files."""
    for root, dirs, files in os.walk('/usr/lib/python3.6/'):
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(root, file)
            print(path)
            with open(path, encoding='utf-8', errors='ignore') as f:
                code = f.read()
                try:
                    names = parse(code)
                except UnparsableError as e:
                    print('unparsable', path, e.error)
                    continue
                except Exception as e:
                    dump_symtable(code)
                    raise
