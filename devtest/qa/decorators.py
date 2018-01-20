"""
Useful execute method decorators.
"""

import sys
from functools import wraps


def debugthis(meth):
    """Decorator for making methods enter the debugger on an exception."""
    @wraps(meth)
    def _lambda(*iargs, **ikwargs):
        try:
            return meth(*iargs, **ikwargs)
        except:  # noqa
            ex, val, tb = sys.exc_info()
            from devtest import debugger
            debugger.post_mortem(tb)
    return _lambda


if __name__ == "__main__":

    @debugthis
    def f():
        print("called f")
        raise KeyError("simulated key error")

    f()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
