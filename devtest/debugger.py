"""
Generic debugger entry point to allow developers to use non-standard debuggers.
Default is to use the built-in debugger, pdb.

set the environment variable PYTHON_DEBUGGER to the package name of the
alternate debugger.

The debugger module should support the "post_mortem" interface.
"""

import sys
import os


class _MakeDebugger:
    def __getattr__(self, name):
        global debugger
        modname = os.environ.get("PYTHON_DEBUGGER", "pdb")
        __import__(modname)
        debugger = sys.modules[modname]
        return getattr(debugger, name)


debugger = _MakeDebugger()


def post_mortem(tb=None):
    if tb is None:
        tb = sys.exc_info()[2]
    if tb is None:
        raise ValueError("A valid traceback must be passed in if no "
                         "exception is being handled.")
    debugger.post_mortem(tb)


def debugger_hook(exc, value, tb):
    if (not hasattr(sys.stderr, "isatty") or
        not sys.stderr.isatty() or exc in (SyntaxError,
                                           IndentationError,
                                           KeyboardInterrupt)):
        sys.__excepthook__(exc, value, tb)
    else:
        post_mortem(tb)


def autodebug(on=True):
    """Enables debugger for all uncaught exceptions."""
    if on:
        sys.excepthook = debugger_hook
    else:
        sys.excepthook = sys.__excepthook__


# Self test
if __name__ == '__main__':
    try:
        raise RuntimeError("Testing")
    except:
        post_mortem()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
