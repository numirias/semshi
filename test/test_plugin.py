import os
import time

import neovim
import pytest


VIMRC = 'test/data/test.vimrc'
SLEEP = 0.1


@pytest.fixture(scope='session')
def plugin_dir(tmpdir_factory):
    return tmpdir_factory.mktemp('test_plugin')


@pytest.fixture(scope="module", autouse=True)
def register_plugin(plugin_dir):
    os.environ['NVIM_RPLUGIN_MANIFEST'] = str(plugin_dir.join('rplugin.vim'))
    child_argv = ['nvim', '-u', VIMRC, '--embed']
    vim = neovim.attach('child', argv=child_argv)
    vim.command('UpdateRemotePlugins')
    vim.quit()
    yield


@pytest.fixture(scope='function')
def vim():
    argv = ['nvim', '-u', VIMRC, '--embed']
    vim = neovim.attach('child', argv=argv)
    return vim


def start_vim(argv=None, file=None):
    if argv is None:
        argv = []
    argv = ['nvim', '-u', VIMRC, '--embed', *argv]
    vim = neovim.attach('child', argv=argv)
    if file is not None:
        fn = file or '/tmp/foo.py'
        vim.command('edit %s' % fn)
    return vim


def wait_for(func, cond, sleep=.001, tries=1000):
    for _ in range(tries):
        res = func()
        if cond(res):
            return res
        time.sleep(sleep)
    raise TimeoutError()


def wait_for_tick(vim):
    tick = host_eval(vim)('plugin._cur_handler._parser.tick')
    wait_for(
        lambda: host_eval(vim)('plugin._cur_handler._parser.tick'),
        lambda x: x > tick
    )


def wait_for_update_thread(vim):
    wait_for(
        lambda: host_eval(vim)('plugin._cur_handler._update_thread.is_alive()'),
        lambda x: not x,
    )


@pytest.fixture
def host_eval(vim, tick=False):
    def func(s):
        if tick:
            wait_for_tick(vim)
        res = vim.call('TestHelperEvalPython', s)
        return res
    return func


def test_commands(vim):
    vim.command('Semshi')
    vim.command('Semshi version')


def test_no_python_file(vim, host_eval):
    assert host_eval('plugin._cur_handler is None')


def test_python_file(vim, host_eval):
    vim.command('edit /tmp/foo.py')
    assert host_eval('plugin._cur_handler is not None')


def test_current_nodes(vim, host_eval):
    vim.command('edit /tmp/foo.py')
    vim.current.buffer[:] = ['aaa', 'bbb']
    node_names = lambda: host_eval('[n.name for n in plugin._cur_handler._parser._nodes]')
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


def test_switch_handler(vim, host_eval):
    vim.command('edit /tmp/foo.py')
    vim.current.buffer[:] = ['aaa', 'bbb']
    node_names = lambda: host_eval('[n.name for n in plugin._cur_handler._parser._nodes]')
    vim.command('edit /tmp/bar.py')
    vim.current.buffer[:] = ['ccc']
    wait_for(node_names, lambda x: x == ['ccc'])
    vim.command('bnext')
    wait_for(node_names, lambda x: x == ['aaa', 'bbb'])


def test_selected_nodes(vim, host_eval):
    vim.command('edit /tmp/foo.py')
    vim.current.buffer[:] = ['aaa', 'aaa']
    vim.call('setpos', '.', [0, 1,1])
    node_positions = lambda: host_eval('[n.pos for n in plugin._cur_handler._selected_nodes]')
    wait_for(node_positions, lambda x: x == [[2, 0]])
    vim.call('setpos', '.', [0, 2,1])
    wait_for(node_positions, lambda x: x == [[1, 0]])


def test_option_active():
    vim = start_vim(['--cmd', 'let g:semshi#active = 0'], file='')
    assert host_eval(vim)('plugin._cur_handler is None')


def test_option_excluded_hl_groups():
    vim = start_vim(['--cmd', 'let g:semshi#excluded_hl_groups = ["global", "imported"]'], file='')
    # TODO Actually, we don't want to inspect the object but check which
    # highlights are applied - but we can't until the neovim API becomes
    # available.
    assert host_eval(vim)('plugin._cur_handler._parser._excluded == ["semshiGlobal", "semshiImported"]')


def test_option_mark_selected_nodes():
    vim = start_vim(['--cmd', 'let g:semshi#mark_selected_nodes = 0'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    wait_for_update_thread(vim)
    assert host_eval(vim)('len(plugin._cur_handler._selected_nodes)') == 0

    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    wait_for_update_thread(vim)
    assert host_eval(vim)('len(plugin._cur_handler._selected_nodes)') == 2

    vim = start_vim(['--cmd', 'let g:semshi#mark_selected_nodes = 2'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa', 'aaa']
    wait_for_update_thread(vim)
    assert host_eval(vim)('len(plugin._cur_handler._selected_nodes)') == 3


def test_option_no_default_builtin_highlight():
    synstack_cmd = 'map(synstack(line("."), col(".")), "synIDattr(v:val, \'name\')")'
    vim = start_vim()
    vim.command('set syntax=python')
    vim.current.buffer[:] = ['len']
    assert vim.eval(synstack_cmd) == []

    vim = start_vim(['--cmd', 'let g:semshi#no_default_builtin_highlight = 0'])
    vim.command('set syntax=python')
    vim.current.buffer[:] = ['len']
    assert vim.eval(synstack_cmd) == ['pythonBuiltin']


def test_option_always_update_all_highlights():
    def ids():
        time.sleep(SLEEP)
        return host_eval(vim)('[n.id for n in plugin._cur_handler._parser._nodes]')
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa', 'aaa']
    old = ids()
    vim.current.buffer[:] = ['aaa', 'aab']
    new = ids()
    assert len(set(old) & set(new)) == 1

    vim = start_vim(['--cmd', 'let g:semshi#always_update_all_highlights = 1'], file='')
    vim.current.buffer[:] = ['aaa', 'aaa']
    old = ids()
    vim.current.buffer[:] = ['aaa', 'aab']
    new = ids()
    assert len(set(old) & set(new)) == 0


def test_cmd_highlight(vim, host_eval):
    vim.command('edit /tmp/foo.py')
    tick = host_eval('plugin._cur_handler._parser.tick')
    vim.command('Semshi highlight')
    assert host_eval('plugin._cur_handler._parser.tick') > tick


def test_syntax_error_sign():
    jump_to_sign = 'exec "sign jump 314000 buffer=" . buffer_number("%")'

    vim = start_vim(['--cmd', 'let g:semshi#error_sign_delay = 0'], file='')
    vim.current.buffer[:] = ['+']
    wait_for_update_thread(vim)
    vim.command(jump_to_sign)
    vim.current.buffer[:] = ['a']
    wait_for_update_thread(vim)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)

    vim = start_vim(['--cmd', 'let g:semshi#error_sign = 0'], file='')
    vim.current.buffer[:] = ['+']
    wait_for_update_thread(vim)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)

    vim = start_vim(['--cmd', 'let g:semshi#error_sign_delay = 1.0'], file='')
    vim.current.buffer[:] = ['+']
    wait_for_update_thread(vim)
    with pytest.raises(neovim.api.nvim.NvimError):
        vim.command(jump_to_sign)


def test_option_tolerate_syntax_errors():
    vim = start_vim(file='')
    vim.current.buffer[:] = ['a+']
    time.sleep(SLEEP)
    num_nodes = host_eval(vim)('len(plugin._cur_handler._parser._nodes)')
    assert num_nodes == 1

    vim = start_vim(['--cmd', 'let g:semshi#tolerate_syntax_errors = 0'], file='')
    vim.current.buffer[:] = ['a+']
    time.sleep(SLEEP)
    num_nodes = host_eval(vim)('len(plugin._cur_handler._parser._nodes)')
    assert num_nodes == 0


def test_rename():
    vim = start_vim(file='')
    vim.current.buffer[:] = ['aaa, aaa, bbb', 'aaa']
    wait_for_tick(vim)
    time.sleep(SLEEP)
    vim.command('Semshi rename xxyyzz')
    time.sleep(SLEEP)
    assert vim.current.buffer[:] == ['xxyyzz, xxyyzz, bbb', 'xxyyzz']
    # The command blocks until an input is received, so we need to call async
    # and sleep
    time.sleep(SLEEP)
    vim.command('Semshi rename', async=True)
    time.sleep(SLEEP)
    vim.feedkeys('CC\n')
    time.sleep(SLEEP)
    assert vim.current.buffer[:] == ['CC, CC, bbb', 'CC']
