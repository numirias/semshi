import os
import time

import neovim
import pytest


VIMRC = 'test/data/test.vimrc'


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


def start_vim(argv=None):
    if argv is None:
        argv = []
    argv = ['nvim', '-u', VIMRC, '--embed', *argv]
    vim = neovim.attach('child', argv=argv)
    return vim


@pytest.fixture
def host_eval(vim):
    def func(s):
        res = vim.call('TestHelperEvalPython', s)
        return res
    return func


def wait_for(func, cond, sleep=.001, tries=1000):
    for _ in range(tries):
        res = func()
        if cond(res):
            return res
        time.sleep(sleep)
    raise TimeoutError()


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
def test_highlights(vim, host_eval):
    """Assert that highlights were applied correctly. This test can only be
    implemented once the neovim API provides a way to retrieve the currently
    active highlights. See: https://github.com/neovim/neovim/issues/6412
    """
    assert False # TODO


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
    wait_for( node_positions, lambda x: x == [[1, 0]])


def test_option_active():
    vim = start_vim(['--cmd', 'let g:semshi#active = 0'])
    vim.command('edit /tmp/foo.py')
    assert host_eval(vim)('plugin._cur_handler is None')


def test_option_excluded_hl_groups():
    vim = start_vim(['--cmd', 'let g:semshi#excluded_hl_groups = ["global", "imported"]'])
    vim.command('edit /tmp/foo.py')
    # TODO Actually, we don't want to inspect the object but check which
    # highlights are applied - but we can't until the neovim API becomes
    # available.
    assert host_eval(vim)('plugin._cur_handler._parser._excluded == ["semshiGlobal", "semshiImported"]')


def test_option_mark_original_node():
    vim = start_vim(['--cmd', 'let g:semshi#mark_original_node = 1'])
    vim.command('edit /tmp/foo.py')
    vim.current.buffer[:] = ['aaa', 'aaa']
    wait_for(
        lambda: host_eval(vim)('len(plugin._cur_handler._selected_nodes)'),
        lambda x: x == 2
    )
