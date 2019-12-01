import os
import time

try:
    import pynvim as neovim
except ImportError:
    import neovim
import pytest


VIMRC = 'test/data/test.vimrc'
SLEEP = 0.1


@pytest.fixture(scope='session')
def plugin_dir(tmpdir_factory):
    return tmpdir_factory.mktemp('test_plugin')


@pytest.fixture(scope='module', autouse=True)
def register_plugin(plugin_dir):
    os.environ['NVIM_RPLUGIN_MANIFEST'] = str(plugin_dir.join('rplugin.vim'))
    child_argv = ['nvim', '-u', VIMRC, '--embed', '--headless']
    vim = neovim.attach('child', argv=child_argv)
    vim.command('UpdateRemotePlugins')
    vim.quit()
    yield


def wait_for(func, cond=None, sleep=.001, tries=1000):
    for _ in range(tries):
        res = func()
        if cond is None:
            if res:
                return
        else:
            if cond(res):
                return res
        time.sleep(sleep)
    raise TimeoutError()


class WrappedVim:

    def __init__(self, vim):
        self._vim = vim

    def __getattr__(self, item):
        return getattr(self._vim, item)

    def host_eval(self, code):
        return self._vim.call('SemshiInternalEval', code)

    def wait_for_update_thread(self):
        wait_for(
            lambda: self.host_eval('plugin._cur_handler._update_thread.is_alive()'),
            lambda x: not x,
        )


@pytest.fixture(scope='function')
def vim():
    argv = ['nvim', '-u', VIMRC, '--embed', '--headless']
    vim = neovim.attach('child', argv=argv)
    return WrappedVim(vim)


@pytest.fixture(scope='function')
def start_vim(tmp_path):
    def f(argv=None, file=None):
        if argv is None:
            argv = []
        argv = ['nvim', '-u', VIMRC, '--embed', '--headless', *argv]
        vim = neovim.attach('child', argv=argv)
        if file is not None:
            fn = file or (tmp_path / 'foo.py')
            vim.command('edit %s' % fn)
        return WrappedVim(vim)
    return f



def test_commands(vim):
    """The :Semshi command is registered and doesn't error"""
    vim.command('Semshi')


@pytest.mark.xfail
def test_no_python_file(vim):
    """If no Python file is open, Semshi doesn't handle the current file"""
    assert vim.host_eval('plugin._cur_handler is None')


def test_python_file(vim, tmp_path):
    """If a Python file is open, Semshi handles the current file"""
    vim.command('edit %s' % (tmp_path / 'foo.py'))
    assert vim.host_eval('plugin._cur_handler is not None')


def test_current_nodes(vim, tmp_path):
    """Changes to the code cause changes to the registered nodes"""
    node_names = lambda: vim.host_eval('[n.name for n in plugin._cur_handler._parser._nodes]')

    vim.command('edit %s' % (tmp_path / 'foo.py'))
    vim.current.buffer[:] = ['aaa', 'bbb']
    wait_for(node_names, lambda x: x == ['aaa', 'bbb'])
    vim.feedkeys('yyp')
    wait_for(node_names, lambda x: x == ['aaa', 'aaa', 'bbb'])
    vim.feedkeys('x')
    wait_for(node_names, lambda x: set(x) == {'aaa', 'aa', 'bbb'})
    vim.feedkeys('ib')
    wait_for(node_names, lambda x: set(x) == {'aaa', 'baa', 'bbb'})


@pytest.mark.xfail
def test_highlights():
    """Assert that highlights were applied correctly. This test can only be
    implemented once the neovim API provides a way to retrieve the currently
    active highlights. See: https://github.com/neovim/neovim/issues/6412
    """
    raise NotImplementedError() # TODO


def test_switch_handler(vim, tmp_path):
    """When switching to a different buffer, the current handlers is updated"""
    node_names = lambda: vim.host_eval('[n.name for n in plugin._cur_handler._parser._nodes]')

    vim.command('edit %s' % (tmp_path / 'foo.py'))
    vim.current.buffer[:] = ['aaa', 'bbb']
    wait_for(node_names, lambda x: x == ['aaa', 'bbb'])
    vim.command('edit %s' % (tmp_path / 'bar.py'))
    vim.current.buffer[:] = ['ccc']
    wait_for(node_names, lambda x: x == ['ccc'])
    vim.command('bnext')
    wait_for(node_names, lambda x: x == ['aaa', 'bbb'])
    vim.command('edit %s' % (tmp_path / 'bar.notpython'))
    assert not vim.eval('get(b:, "semshi_attached", v:false)')
    assert vim.host_eval('plugin._cur_handler is None')
    assert vim.host_eval('len(plugin._handlers)') == 2
    vim.command('bprev')
    assert vim.eval('get(b:, "semshi_attached", v:false)')
    assert not vim.host_eval('plugin._cur_handler is None')


def test_wipe_buffer(vim, tmp_path):
    """When a buffer is wiped out, the handler should be removed."""
    # Without calling a Semshi command first, the subsequent assertions
    # accessing the plugin may fail
    vim.command('Semshi')
    assert vim.host_eval('len(plugin._handlers)') == 0
    vim.command('edit %s' % (tmp_path / 'foo.py'))
    assert vim.host_eval('len(plugin._handlers)') == 1
    vim.command('bwipeout %s' % (tmp_path / 'foo.py'))
    assert vim.host_eval('len(plugin._handlers)') == 0


def test_cursormoved_before_bufenter(vim, tmp_path):
    """When CursorMoved is triggered before BufEnter, switch the buffer."""
    vim.command('edit %s' % (tmp_path / 'foo.py'))
    vim.command('new %s' % (tmp_path / 'bar.py'))
    vim.command('q')
    assert vim.host_eval('plugin._cur_handler._buf_num') == 1


def test_selected_nodes(vim, tmp_path):
    """When moving the cursor above a node, it's registered as selected"""
    node_positions = lambda: vim.host_eval('[n.pos for n in plugin._cur_handler._selected_nodes]')

    vim.command('edit %s' % (tmp_path / 'foo.py'))
    vim.current.buffer[:] = ['aaa', 'aaa']
    vim.call('setpos', '.', [0, 1,1])
    wait_for(node_positions, lambda x: x == [[2, 0]])
    vim.call('setpos', '.', [0, 2,1])
    wait_for(node_positions, lambda x: x == [[1, 0]])


def test_option_filetypes(start_vim):
    vim = start_vim(file='foo.py')
    assert vim.host_eval('plugin._cur_handler is not None')

    vim = start_vim(['--cmd', 'let g:semshi#filetypes = []'], file='foo.py')
    assert vim.host_eval('plugin._cur_handler is None')

    vim = start_vim(['--cmd', 'let g:semshi#filetypes = ["html", "php"]'], file='foo.py')
    assert vim.host_eval('plugin._cur_handler is None')

    vim = start_vim(['--cmd', 'let g:semshi#filetypes = ["html", "php"]'], file='foo.php')
    assert vim.host_eval('plugin._cur_handler is not None')


def test_option_excluded_hl_groups(start_vim):
    vim = start_vim(['--cmd', 'let g:semshi#excluded_hl_groups = ["global", "imported"]'], file='')
    # TODO Actually, we don't want to inspect the object but check which
    # highlights are applied - but we can't until the neovim API becomes
    # available.
    assert vim.host_eval('plugin._cur_handler._parser._excluded == ["semshiGlobal", "semshiImported"]')


def test_option_mark_selected_nodes(start_vim):
    vim = start_vim(['--cmd', 'let g:semshi#mark_selected_nodes = 0'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    vim.wait_for_update_thread()
    assert vim.host_eval('len(plugin._cur_handler._selected_nodes)') == 0

    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    vim.wait_for_update_thread()
    assert vim.host_eval('len(plugin._cur_handler._selected_nodes)') == 2

    vim = start_vim(['--cmd', 'let g:semshi#mark_selected_nodes = 2'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    vim.wait_for_update_thread()
    assert vim.host_eval('len(plugin._cur_handler._selected_nodes)') == 3


def test_option_no_default_builtin_highlight(start_vim):
    synstack_cmd = 'map(synstack(line("."), col(".")), "synIDattr(v:val, \'name\')")'
    vim = start_vim(file='')
    vim.current.buffer[:] = ['len']
    assert vim.eval(synstack_cmd) == []

    vim = start_vim(['--cmd', 'let g:semshi#no_default_builtin_highlight = 0'], file='')
    vim.current.buffer[:] = ['len']
    assert vim.eval(synstack_cmd) == ['pythonBuiltin']


def test_option_always_update_all_highlights(start_vim):
    def get_ids():
        time.sleep(SLEEP)
        return vim.host_eval('[n.id for n in plugin._cur_handler._parser._nodes]')
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa', 'aaa']
    old = get_ids()
    vim.current.buffer[:] = ['aaa', 'aab']
    new = get_ids()
    assert len(set(old) & set(new)) == 1

    vim = start_vim(['--cmd', 'let g:semshi#always_update_all_highlights = 1'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa']
    old = get_ids()
    vim.current.buffer[:] = ['aaa', 'aab']
    new = get_ids()
    assert len(set(old) & set(new)) == 0


def test_cmd_highlight(vim, tmp_path):
    vim.command('edit %s' % (tmp_path / 'foo.py'))
    tick = vim.host_eval('plugin._cur_handler._parser.tick')
    vim.command('Semshi highlight')
    assert vim.host_eval('plugin._cur_handler._parser.tick') > tick


def test_syntax_error_sign(start_vim):
    jump_to_sign = 'exec "sign jump 314000 buffer=" . buffer_number("%")'

    vim = start_vim(['--cmd', 'let g:semshi#error_sign_delay = 0'], file='')
    vim.current.buffer[:] = ['+']
    vim.wait_for_update_thread()
    time.sleep(SLEEP)
    vim.command(jump_to_sign)
    vim.current.buffer[:] = ['a']
    vim.wait_for_update_thread()
    time.sleep(SLEEP)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)

    vim = start_vim(['--cmd', 'let g:semshi#error_sign = 0'], file='')
    vim.current.buffer[:] = ['+']
    vim.wait_for_update_thread()
    time.sleep(SLEEP)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)

    vim = start_vim(['--cmd', 'let g:semshi#error_sign_delay = 1.0'], file='')
    vim.current.buffer[:] = ['+']
    vim.wait_for_update_thread()
    time.sleep(SLEEP)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)


def test_option_tolerate_syntax_errors(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = ['a+']
    time.sleep(SLEEP)
    num_nodes = vim.host_eval('len(plugin._cur_handler._parser._nodes)')
    assert num_nodes == 1

    vim = start_vim(['--cmd', 'let g:semshi#tolerate_syntax_errors = 0'], file='')
    vim.current.buffer[:] = ['a+']
    time.sleep(SLEEP)
    num_nodes = vim.host_eval('len(plugin._cur_handler._parser._nodes)')
    assert num_nodes == 0


def test_option_update_delay_factor(start_vim):
    vim = start_vim(['--cmd', 'let g:semshi#update_delay_factor = 2'], file='')
    time.sleep(SLEEP)
    vim.current.buffer[:] = ['foo']
    time.sleep(SLEEP)
    num_nodes = vim.host_eval('len(plugin._cur_handler._parser._nodes)')
    assert num_nodes == 0


def test_option_self_to_attribute(start_vim):
    buf = ['class Foo:', ' def foo(self): self.bar, self.bar']
    selected = lambda: vim.host_eval('[n.pos for n in plugin._cur_handler._selected_nodes]')

    vim = start_vim(file='')
    vim.current.buffer[:] = buf
    vim.current.window.cursor = [2, 16]
    wait_for(selected, lambda x: x == [[2, 31]])

    vim = start_vim(['--cmd', 'let g:semshi#self_to_attribute = 0'], file='')
    vim.current.buffer[:] = buf
    vim.current.window.cursor = [2, 16]
    wait_for(selected, lambda x: x == [[2, 9], [2, 26]])


def test_rename(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa, aaa, bbb', 'aaa']
    time.sleep(SLEEP)
    vim.command('Semshi rename xxyyzz')
    time.sleep(SLEEP)
    assert vim.current.buffer[:] == ['xxyyzz, xxyyzz, bbb', 'xxyyzz']
    # The command blocks until an input is received, so we need to call async
    # and sleep
    time.sleep(SLEEP)
    vim.command('Semshi rename', async_=True)
    time.sleep(SLEEP)
    vim.feedkeys('CC\n')
    time.sleep(SLEEP)
    assert vim.current.buffer[:] == ['CC, CC, bbb', 'CC']


def test_goto(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = [
        'class Foo:',
        ' def foo(self): pass',
        'class Bar: pass',
        'class Baz: pass',
    ]
    time.sleep(SLEEP)
    vim.command('Semshi goto function next')
    wait_for(lambda: vim.current.window.cursor == [2, 1])
    vim.command('Semshi goto class prev')
    wait_for(lambda: vim.current.window.cursor == [1, 0])
    vim.command('Semshi goto class last')
    wait_for(lambda: vim.current.window.cursor == [4, 0])
    vim.command('Semshi goto class first')
    wait_for(lambda: vim.current.window.cursor == [1, 0])


def test_goto_name(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa, aaa, aaa']
    time.sleep(SLEEP)
    vim.command('Semshi goto name next')
    wait_for(lambda: vim.current.window.cursor == [1, 5])
    time.sleep(SLEEP)
    vim.command('Semshi goto name next')
    wait_for(lambda: vim.current.window.cursor == [1, 10])
    time.sleep(SLEEP)
    vim.command('Semshi goto name next')
    wait_for(lambda: vim.current.window.cursor == [1, 0])
    time.sleep(SLEEP)
    vim.command('Semshi goto name prev')
    wait_for(lambda: vim.current.window.cursor == [1, 10])
    time.sleep(SLEEP)
    vim.command('Semshi goto name prev')
    wait_for(lambda: vim.current.window.cursor == [1, 5])


def test_goto_hl_group(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = [
        'foo = 1',
        'def x(y): pass',
    ]
    time.sleep(SLEEP)
    vim.command('Semshi goto parameterUnused first')
    wait_for(lambda: vim.current.window.cursor == [2, 6])


def test_goto_error(start_vim):
    vim = start_vim(['--cmd', 'let g:semshi#error_sign_delay = 0'], file='')
    vim.current.buffer[:] = ['a', '+']
    vim.wait_for_update_thread()
    assert vim.current.window.cursor == [1, 0]
    vim.command('Semshi goto error')
    assert vim.current.window.cursor == [2, 0]


def test_clear(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa']
    time.sleep(SLEEP)
    vim.command('Semshi clear')
    assert vim.host_eval('len(plugin._cur_handler._parser._nodes)') == 0


def test_enable_disable(start_vim):
    def num_nodes(n):
        def f():
            return vim.host_eval('len(plugin._cur_handler._parser._nodes)') == n
        return f
    def no_handler():
        return vim.host_eval('plugin._cur_handler is None')

    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa']
    wait_for(num_nodes(1))
    vim.command('Semshi disable')
    wait_for(no_handler)
    vim.command('Semshi enable')
    wait_for(num_nodes(1))
    vim.command('Semshi disable')
    wait_for(no_handler)
    vim.command('Semshi enable')
    wait_for(num_nodes(1))


def test_enable_by_filetype(start_vim):
    vim = start_vim(file='foo.ext')
    vim.current.buffer[:] = ['aaa']
    assert vim.host_eval('plugin._cur_handler is None')
    assert vim.host_eval('len(plugin._handlers)') == 0
    vim.command('set ft=python')
    assert vim.eval('b:semshi_attached')
    assert vim.host_eval('plugin._cur_handler is not None')
    assert vim.host_eval('len(plugin._handlers)') == 1
    vim.command('set ft=php')
    assert not vim.eval('b:semshi_attached')
    assert vim.host_eval('plugin._cur_handler is None')
    assert vim.host_eval('len(plugin._handlers)') == 0


def test_pause(start_vim):
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa']
    time.sleep(SLEEP)
    vim.command('Semshi pause')
    assert vim.host_eval('len(plugin._cur_handler._parser._nodes)') == 1
    vim.current.buffer[:] = ['aaa, bbb']
    time.sleep(SLEEP)
    assert vim.host_eval('len(plugin._cur_handler._parser._nodes)') == 1


def test_bug_21(start_vim):
    vim = start_vim(file='foo.ext')
    with pytest.raises(neovim.api.nvim.NvimError, match='.*not enabled.*'):
        vim.command('Semshi goto error')
