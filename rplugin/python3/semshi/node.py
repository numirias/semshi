import builtins
from itertools import count


hl_groups = {}

def group(s):
    label = 'semshi' + s[0].capitalize() + s[1:]
    hl_groups[s] = label
    return label

UNRESOLVED = group('unresolved')
ATTRIBUTE = group('attribute')
BUILTIN = group('builtin')
FREE = group('free')
GLOBAL = group('global')
PARAMETER = group('parameter')
PARAMETER_UNUSED = group('parameterUnused')
SELF = group('self')
IMPORTED = group('imported')
LOCAL = group('local')
SELECTED = group('selected')

more_builtins = {'__file__', '__path__', '__cached__'}
builtins = set(vars(builtins)) | more_builtins


class Node:
    """A node in the source code.

    """
    # Highlight ID for selected nodes
    MARK_ID = 31400
    # Highlight ID counter (chosen arbitrarily)
    id_counter = count(314001)

    __slots__ = ['id', 'name', 'lineno', 'col', 'end', 'env',
                 'symname', 'symbol', 'hl_group', 'target', '_tup']

    def __init__(self, name, lineno, col, env, target=None, hl_group=None):
        self.id = next(Node.id_counter)
        self.name = name
        self.lineno = lineno
        self.col = col
        # Encode the name to get the byte length, not the number of chars
        self.end = self.col + len(self.name.encode('utf-8'))
        self.env = env
        self.symname = self._make_symname(name)
        # The target node for an attribute
        self.target = target
        if hl_group == ATTRIBUTE:
            self.symbol = None
        else:
            try:
                self.symbol = self.env[-1].lookup(self.symname)
            except KeyError as exc:
                # Set dummy hl group, so all fields in __repr__ are defined.
                self.hl_group = '?'
                raise Exception(
                    '%s can\'t lookup "%s"' % (self, self.symname)
                ) from exc
        if hl_group is not None:
            self.hl_group = hl_group
        else:
            self.hl_group = self._make_hl_group()
        self.update_tup()

    def update_tup(self):
        """Update tuple used for comparing with other nodes."""
        self._tup = (self.lineno, self.col, self.hl_group, self.name)

    def __lt__(self, other):
        return self._tup < other._tup # pylint: disable=protected-access

    def __eq__(self, other):
        return self._tup == other._tup # pylint: disable=protected-access

    def __hash__(self):
        # Currently only required for tests
        return hash(self._tup)

    def __repr__(self):
        return '<%s %s %s (%s, %s) %d>' % (
            self.name,
            self.hl_group[6:],
            '.'.join([x.get_name() for x in self.env]),
            self.lineno,
            self.col,
            self.id,
        )

    def _make_hl_group(self):
        """Return highlight group the node belongs to."""
        sym = self.symbol
        name = self.name
        if sym.is_parameter():
            table = self.env[-1]
            # We have seen the node, so remove from unused parameters
            table.unused_params.pop(self.name, None)
            try:
                self_param = table.self_param
            except AttributeError:
                pass
            else:
                if self_param == name:
                    return SELF
            return PARAMETER
        if sym.is_free():
            table = self._ref_function_table()
            if table is not None:
                table.unused_params.pop(self.name, None)
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
                if global_sym.is_assigned():
                    return GLOBAL
                if name in builtins:
                    return BUILTIN
                if global_sym.is_imported():
                    return IMPORTED
                return UNRESOLVED
        if name in builtins:
            return BUILTIN
        return UNRESOLVED

    def _make_symname(self, name):
        """Return actual symbol name.

        The symname may be different due to name mangling.
        """
        # Check if the name is a candidate for name mangling
        if not name.startswith('__') or name.endswith('__'):
            return name
        try:
            cls = next(t for t in reversed(self.env) if
                       t.get_type() == 'class')
        except StopIteration:
            # Not inside a class, so no candidate for name mangling
            return name
        symname = '_' + cls.get_name().lstrip('_') + name
        return symname

    def _ref_function_table(self):
        """Return enclosing function table."""
        for table in reversed(self.env):
            try:
                symbol = table.lookup(self.name)
            except KeyError:
                continue
            if symbol.is_parameter():
                return table
        return None

    def base_table(self):
        """Return base symtable.

        The base symtable is the lowest scope with an associated symbol.
        """
        if self.hl_group == ATTRIBUTE:
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
