import gc

try:
    import pynvim as neovim
except ImportError:
    import neovim
import pytest


@neovim.plugin
class TestHelperPlugin:
    """A helper plugin to facilitate tests that access the plugin running in
    the context of the plugin host (which is why it can't be inspected
    directly).
    """
    def __init__(self, vim):
        self._vim = vim
        self._plugin = None

    @neovim.autocmd('VimEnter', pattern='*', sync=True)
    def event_vim_enter(self):
        """Find and retain the plugin instance."""
        # Don't import semshi on top so it's not collected as a plugin again
        from semshi.plugin import Plugin
        # Using the garbage collector interface to find the instance is a bit
        # hacky, but works reasonably well and doesn't require changes to the
        # plugin code itself.
        for obj in gc.get_objects():
            if isinstance(obj, Plugin):
                self._plugin = obj
                return
        raise Exception('Can\'t find plugin instance.')

    @neovim.function('TestHelperEvalPython', sync=True)
    def helper_eval_python(self, args):
        """Eval Python code in the plugin host context and return result.

        The local variable "plugin" holds a reference to the plugin instance
        which is useful to inspect the plugin.
        """
        plugin = self._plugin
        return eval(args[0])
