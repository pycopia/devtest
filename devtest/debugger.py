# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Generic debugger entry point to allow developers to use non-standard debuggers.
Default is to use the built-in debugger, pdb.

set the environment variable PYTHON_DEBUGGER to the package name of the
alternate debugger.

The debugger module should support the "post_mortem" interface.
"""

import sys
import os

# Reset excepthook to default. Some Linux distros put something there
# that can interfere with this. They think they're being helpful, but
# they are not.
sys.excepthook = sys.__excepthook__


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
        DEBUG("Uncaught exception:", exc.__name__, ":", value)
        post_mortem(tb)


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

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
