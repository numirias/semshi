import builtins
from itertools import count


groups = {}

def group(s):
    label = 'semshi%s' % s.title()
    groups[s] = label
    return label

UNRESOLVED = group('unresolved')
ATTRIBUTE = group('attribute')
BUILTIN = group('builtin')
FREE = group('free')
GLOBAL = group('global')
PARAMETER = group('parameter')
SELF = group('self')
IMPORTED = group('imported')
LOCAL = group('local')
SELECTED = group('selected')

more_builtins = {'__file__', '__path__', '__cached__'}
builtins = set(vars(builtins)) | more_builtins


class Node:

    MARK_ID = 31400
    id_counter = count(314001)

    __slots__ = ['id', 'name', 'lineno', 'col', 'end', 'env', 'is_attr',
                 'symname', 'symbol', 'hl_group', 'target', '_tup']

    def __init__(self, name, lineno, col, env, is_attr=False, target=None):
        self.id = next(Node.id_counter)
        self.name = name
        self.lineno = lineno
        self.col = col
        # We need the byte length  (TODO is there a faster way?)
        self.end = self.col + len(self.name.encode('utf-8'))
        self.env = env
        self.is_attr = is_attr
        self.symname = self._make_symname(name)
        self.target = target
        if is_attr:
            self.symbol = None
        else:
            table = self.env[-1]
            try:
                self.symbol = table.lookup(self.symname)
            except KeyError:
                # TODO Maybe just write log instead of raising exception?
                raise Exception('%s can\'t lookup "%s"' % (self, self.symname))
        self.hl_group = self._make_hl_group()
        self._tup = (self.lineno, self.col, self.hl_group, self.name)

    def __lt__(self, other):
        return self._tup < other._tup # pylint: disable=protected-access

    def __eq__(self, other):
        return self._tup == other._tup # pylint: disable=protected-access

    def __hash__(self):
        # TODO Currently only required for tests
        return hash(self._tup)

    def __repr__(self):
        return '<%s %s %s (%s, %s) %d>' % (
            self.name,
            self.hl_group[6:], # TODO hl_group isn't always defined
            '.'.join([x.get_name() for x in self.env]),
            self.lineno,
            self.col,
            self.id,
        )

    def _make_hl_group(self):
        if self.is_attr:
            return ATTRIBUTE
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
            return PARAMETER
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
                if global_sym.is_assigned():
                    return GLOBAL
                if name in builtins:
                    return BUILTIN
                return UNRESOLVED
        if name in builtins:
            return BUILTIN
        return UNRESOLVED

    def _make_symname(self, name):
        """Return actual symbol name."""
        # Check if we need to apply name mangling
        if not name.startswith('__') or name.endswith('__'):
            return name
        try:
            cls = next(t for t in reversed(self.env) if
                       t.get_type() == 'class')
        except StopIteration:
            return name
        symname = '_' + cls.get_name().lstrip('_') + name
        return symname

    def base_table(self):
        """Return base symtable.

        The base symtable is the lowest scope with an associated symbol.
        """
        if self.is_attr:
            return self.env[-1]
        if self.symbol.is_global():
            return self.env[0]
        if self.symbol.is_local() and not self.symbol.is_free():
            return self.env[-1]
        for table in reversed(self.env):
            # Class scopes don't extend to enclosed scopes
            if table.get_type() == 'class':
                continue
            try:
                symbol = table.lookup(self.name)
            except KeyError:
                continue
            if symbol.is_local() and not symbol.is_free():
                return table
        return None

    @property
    def pos(self):
        return (self.lineno, self.col)
