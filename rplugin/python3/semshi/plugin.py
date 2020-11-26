from functools import partial, wraps

try:
    import pynvim as neovim
except ImportError:
    import neovim

from .handler import BufferHandler
from .node import hl_groups


_subcommands = {}


def subcommand(func=None, needs_handler=False, silent_fail=True):
    """Decorator to register `func` as a ":Semshi [...]" subcommand.

    If `needs_handler`, the subcommand will fail if no buffer handler is
    currently active. If `silent_fail`, it will fail silently, otherwise an
    error message is printed.
    """
    if func is None:
        return partial(
            subcommand, needs_handler=needs_handler, silent_fail=silent_fail)
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # pylint: disable=protected-access
        if self._options is None:
            self._init_with_vim()
        if needs_handler and self._cur_handler is None:
            if not silent_fail:
                self.echo_error('Semshi is not enabled in this buffer!')
            return
        func(self, *args, **kwargs)
    _subcommands[func.__name__] = wrapper
    return wrapper


@neovim.plugin
class Plugin:
    """Semshi Neovim plugin.

    The plugin handles vim events and commands, and delegates them to a buffer
    handler. (Each buffer is handled by a semshi.BufferHandler instance.)
    """

    def __init__(self, vim):
        self._vim = vim
        # A mapping (buffer number -> buffer handler)
        self._handlers = {}
        # The currently active buffer handler
        self._cur_handler = None
        self._options = None

    def _init_with_vim(self):
        """Initialize with vim available.

        Initialization code which interacts with vim can't be safely put in
        __init__ because vim itself may not be fully started up.
        """
        self._options = Options(self._vim)

    def echo(self, *msgs):
        msg = ' '.join([str(m) for m in msgs])
        self._vim.out_write(msg + '\n')

    def echo_error(self, *msgs):
        msg = ' '.join([str(m) for m in msgs])
        self._vim.err_write(msg + '\n')

    # Must not be async here because we have to make sure that switching the
    # buffer handler is completed before other events are handled.
    @neovim.function('SemshiBufEnter', sync=True)
    def event_buf_enter(self, args):
        buf_num, view_start, view_stop = args
        self._select_handler(buf_num)
        self._update_viewport(view_start, view_stop)
        self._cur_handler.update()
        self._mark_selected()

    @neovim.function('SemshiBufLeave', sync=True)
    def event_buf_leave(self, _):
        self._cur_handler = None

    @neovim.function('SemshiBufWipeout', sync=True)
    def event_buf_wipeout(self, args):
        self._remove_handler(args[0])

    @neovim.function('SemshiVimResized', sync=False)
    def event_vim_resized(self, args):
        self._update_viewport(*args)
        self._mark_selected()

    @neovim.function('SemshiCursorMoved', sync=False)
    def event_cursor_moved(self, args):
        if self._cur_handler is None:
            # CursorMoved may trigger before BufEnter, so select the buffer if
            # we didn't enter it yet.
            self.event_buf_enter((self._vim.current.buffer.number, *args))
            return
        self._update_viewport(*args)
        self._mark_selected()

    @neovim.function('SemshiTextChanged', sync=False)
    def event_text_changed(self, _):
        if self._cur_handler is None:
            return
        # Note: TextChanged event doesn't trigger if text was changed in
        # unfocused buffer via e.g. nvim_buf_set_lines().
        self._cur_handler.update()

    @neovim.autocmd('VimLeave', sync=True)
    def event_vim_leave(self):
        for handler in self._handlers.values():
            handler.shutdown()

    @neovim.command('Semshi', nargs='*', complete='customlist,SemshiComplete',
                    sync=True)
    def cmd_semshi(self, args):
        if not args:
            self.echo('This is semshi.')
            return
        try:
            func = _subcommands[args[0]]
        except KeyError:
            self.echo_error('Subcommand not found: %s' % args[0])
            return
        func(self, *args[1:])

    @staticmethod
    @neovim.function('SemshiComplete', sync=True)
    def func_complete(arg):
        lead, *_ = arg
        return [c for c in _subcommands if c.startswith(lead)]

    @neovim.function('SemshiInternalEval', sync=True)
    def _internal_eval(self, args):
        """Eval Python code in plugin context.

        Only used for testing."""
        plugin = self # noqa pylint: disable=unused-variable
        return eval(args[0]) # pylint: disable=eval-used

    @subcommand
    def enable(self):
        self._attach_listeners()
        self._select_handler(self._vim.current.buffer)
        self._update_viewport(*self._vim.eval('[line("w0"), line("w$")]'))
        self.highlight()

    @subcommand(needs_handler=True)
    def disable(self):
        self.clear()
        self._detach_listeners()
        self._cur_handler = None
        self._remove_handler(self._vim.current.buffer)

    @subcommand
    def toggle(self):
        if self._listeners_attached():
            self.disable()
        else:
            self.enable()

    @subcommand(needs_handler=True)
    def pause(self):
        self._detach_listeners()

    @subcommand(needs_handler=True, silent_fail=False)
    def highlight(self):
        self._cur_handler.update(force=True, sync=True)

    @subcommand(needs_handler=True)
    def clear(self):
        self._cur_handler.clear_highlights()

    @subcommand(needs_handler=True, silent_fail=False)
    def rename(self, new_name=None):
        self._cur_handler.rename(self._vim.current.window.cursor, new_name)

    @subcommand(needs_handler=True, silent_fail=False)
    def goto(self, *args, **kwargs):
        self._cur_handler.goto(*args, **kwargs)

    @subcommand(needs_handler=True, silent_fail=False)
    def error(self):
        self._cur_handler.show_error()

    @subcommand
    def status(self):
        self.echo(
            'current handler: {handler}\n'
            'handlers: {handlers}'
            .format(
                handler=self._cur_handler,
                handlers=self._handlers
            )
        )

    def _select_handler(self, buf_or_buf_num):
        """Select handler for `buf_or_buf_num`."""
        if isinstance(buf_or_buf_num, int):
            buf = None
            buf_num = buf_or_buf_num
        else:
            buf = buf_or_buf_num
            buf_num = buf.number
        try:
            handler = self._handlers[buf_num]
        except KeyError:
            if buf is None:
                buf = self._vim.buffers[buf_num]
            handler = BufferHandler(buf, self._vim, self._options)
            self._handlers[buf_num] = handler
        self._cur_handler = handler

    def _remove_handler(self, buf_or_buf_num):
        """Remove handler for buffer with the number `buf_num`."""
        if isinstance(buf_or_buf_num, int):
            buf_num = buf_or_buf_num
        else:
            buf_num = buf_or_buf_num.number
        try:
            handler = self._handlers.pop(buf_num)
        except KeyError:
            return
        else:
            handler.shutdown()

    def _update_viewport(self, start, stop):
        self._cur_handler.viewport(start, stop)

    def _mark_selected(self):
        if not self._options.mark_selected_nodes:
            return
        self._cur_handler.mark_selected(self._vim.current.window.cursor)

    def _attach_listeners(self):
        self._vim.call('semshi#buffer_attach')

    def _detach_listeners(self):
        self._vim.call('semshi#buffer_detach')

    def _listeners_attached(self):
        """Return whether event listeners are attached to the current buffer.
        """
        return self._vim.eval('get(b:, "semshi_attached", v:false)')


class Options:
    """Plugin options.

    The options will only be read and set once on init.
    """
    _defaults = {
        'filetypes': ['python'],
        'excluded_hl_groups': ['local'],
        'mark_selected_nodes': 1,
        'no_default_builtin_highlight': True,
        'simplify_markup': True,
        'error_sign': True,
        'error_sign_delay': 1.5,
        'always_update_all_highlights': False,
        'tolerate_syntax_errors': True,
        'update_delay_factor': .0,
        'self_to_attribute': True,
    }

    def __init__(self, vim):
        for key, val_default in Options._defaults.items():
            val = vim.vars.get('semshi#' + key, val_default)
            # vim.vars doesn't support setdefault(), so set value manually
            vim.vars['semshi#' + key] = val
            try:
                converter = getattr(Options, '_convert_' + key)
            except AttributeError:
                pass
            else:
                val = converter(val)
            setattr(self, key, val)

    @staticmethod
    def _convert_excluded_hl_groups(items):
        try:
            return [hl_groups[g] for g in items]
        except KeyError as e:
            # TODO Use err_write instead?
            raise Exception(
                '"%s" is an unknown highlight group.' % e.args[0]
            ) from e
