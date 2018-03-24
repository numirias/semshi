import builtins
from .util import logger

def label(s):
    return 'semshi%s' % s.title()


UNRESOLVED = label('unresolved')
ATTR = label('attr')
BUILTIN = label('builtin')
FREE = label('free')
GLOBAL = label('global')
PARAM = label('param')
SELF = label('self')
IMPORTED = label('imported')
LOCAL = label('local')
MARKED = label('marked')

more_builtins = {'__file__', '__path__', '__cached__'}
builtins = set(vars(builtins)) | more_builtins


class Node:

    MARK_ID = 31400
    next_id = 314001

    __slots__ = ['id','env', 'lineno', 'col', 'name', 'end', 'is_attr',
                 'symname', 'symbol', 'hl_group', '_tup', 'target']

    def __init__(self, id, lineno, col, env, is_attr=False, target=None):
        self.id = Node.next_id
        Node.next_id += 1
        self.env = env
        self.lineno = lineno
        self.col = col
        self.name = id
        self.end = self.col + len(bytes(self.name, 'utf-8'))
        self.is_attr = is_attr
        self.symname = self.make_symname()
        self.target = target
        if is_attr:
            self.symbol = None
        else:
            table = self.env[-1]
            try:
                self.symbol = table.lookup(self.symname)
            except KeyError:
                raise Exception('%s can\'t lookup "%s".' % (self, self.symname))
        self.hl_group = self.make_hl_group()
        self._tup = (self.lineno, self.col, self.hl_group, self.name)
        # self.id = hash(self._tup) % 1000000000

    def make_tup(self):
        self._tup = (self.lineno, self.col, self.hl_group, self.name)

    def __lt__(self, other):
        return self._tup < other._tup 

    def __eq__(self, other):
        return self._tup == other._tup

    def __hash__(self):
        # TODO Only kept so tests run properly
        return hash(self._tup)

    def __repr__(self):
        return '<%s %s %s (%s, %s) %d>' % (self.name, self.hl_group[6:], '.'.join([x.get_name() for x in self.env]), self.lineno, self.col, self.id)

    @property
    def pos(self):
        return (self.lineno, self.col)

    def make_hl_group(self):
        if self.is_attr:
            return ATTR
        sym = self.symbol
        name = self.name
        if sym.is_parameter():
            try:
                self_param = self.env[-1].self_param
            except AttributeError:
                pass
            else:
                if self_param == name:
                    return SELF
            return PARAM
        if sym.is_free(): # TODO
            return FREE
        if sym.is_imported():
            return IMPORTED
        if sym.is_local() and not sym.is_global():
            return LOCAL
        if sym.is_global():
            try:
                global_sym = self.env[0].lookup(name)
            except KeyError:
                pass
            else:
                if global_sym.is_imported():
                    return IMPORTED
                # TODO simplify?
                if not global_sym.is_assigned():
                    if name in builtins:
                        return BUILTIN
                    else:
                        return UNRESOLVED
                return GLOBAL
        if self.base_table() is not self.env[0]:
            # TODO Does this ever happen?
            raise Exception('Base table exception (shouldn\'t happen)')
            return FREE
        if name in builtins:
            return BUILTIN
        else:
            return UNRESOLVED

    def make_symname(self):
        name = self.name
        if not (name.startswith('__') and not name.endswith('__')):
            return name
        try:
            cls = next(t for t in reversed(self.env) if t.get_type() == 'class')
        except StopIteration:
            return name
        symname = '_' + cls.get_name().lstrip('_') + name
        return symname

    def hl(self, marked=False):
        if marked:
            return (MARKED, self.lineno - 1, self.col, self.end, self.MARK_ID)
        # return (self.hl_group, self.lineno - 1, self.col, self.end, self.id)
        return (self.id, self.hl_group, self.lineno - 1, self.col, self.end)

    def base_table(self):
        # logger.debug('base table of %d', self.id)
        if self.is_attr:
            return self.env[-1]
        if self.symbol.is_global():
            return self.env[0]
        if self.symbol.is_local() and not self.symbol.is_free():
            return self.env[-1]
        for table in reversed(self.env):
            # Classes scopes don't extend to enclosed scopes
            if table.get_type() == 'class':
                continue
            try:
                symbol = table.lookup(self.name)
            except KeyError:
                continue
            if symbol.is_local() and not symbol.is_free():
                return table
        return None
