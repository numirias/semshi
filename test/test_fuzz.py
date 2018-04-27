import os
from semshi.parser import UnparsableError

import pytest

from .conftest import parse, dump_symtable


@pytest.mark.fuzz
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
