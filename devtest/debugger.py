"""
Debugger hooks for framework.

Uses the debugger from the open-source `elicit` package.

Performs lazy loading of the debugger is it isn't imported at runner load time.
"""

import sys

from elicit import debugger
from elicit.debugger import DebuggerQuit  # noqa

# Reset excepthook to default. Some Linux distros put something there
# that can interfere with this. They think they're being helpful, but
# they are not.
sys.excepthook = sys.__excepthook__

# Global, singleton debugger for framework.
_dbg = None


def get_debugger(io=None):
    global _dbg
    if _dbg is None:
        dbg = debugger.Debugger(io=io)
        _dbg = dbg
    _dbg.reset()
    return _dbg


def post_mortem(tb=None, io=None):
    "Start debugging at the given traceback."
    exc = val = None
    if tb is None:
        exc, val, tb = sys.exc_info()
    if tb is None:
        raise ValueError("A valid traceback must be passed if no "
                         "exception is being handled.")
    dbg = get_debugger(io)

    while tb.tb_next is not None:
        tb = tb.tb_next
    if exc and val:
        dbg.print_exc("Post Mortem Exception: ", val)
    dbg.interaction(tb.tb_frame, tb, val)


def from_exception(ex, io=None):
    """Start debugging from the place of the given exception instance."""
    tb = ex.__traceback__
    dbg = get_debugger(io)
    while tb.tb_next is not None:
        tb = tb.tb_next
    dbg.print_exc("", ex)
    dbg.interaction(tb.tb_frame, tb, ex)


def set_trace(frame=None, start=0):
    get_debugger().set_trace(frame=frame, start=start)


# Invoke our debugger instance when setting breakpoints.
sys.breakpointhook = set_trace


def debugger_hook(exc, value, tb):
    if (not hasattr(sys.stderr, "isatty") or not sys.stderr.isatty() or
            exc in (SyntaxError, IndentationError, KeyboardInterrupt)):
        sys.__excepthook__(exc, value, tb)
    else:
        DEBUG("Uncaught exception:", exc.__name__, ":", value)
        from_exception(value)


def autodebug(on=True):
    """Enables debugger for all uncaught exceptions."""
    if on:
        sys.excepthook = debugger_hook
    else:
        sys.excepthook = sys.__excepthook__


def DEBUG(*args, **kwargs):
    """You can use this instead of 'print' when debugging. Prints to stderr.

    Emits nothing if run in "optimized" mode.
    """
    if __debug__:
        kwargs["file"] = sys.stderr
        print("DEBUG", *args, **kwargs)


# Self test
if __name__ == '__main__':
    try:
        raise RuntimeError("Testing")
    except:  # noqa
        post_mortem()
