# Likely, the original license is PSF.
"""Custom REPL copied from code module and modified.
"""

import sys
import os
import readline
import traceback
from codeop import CommandCompiler

from jedi import Interpreter

from devtest import debugger
from devtest.ui.simpleui import ConsoleIO
from devtest.utils import colors


class InteractiveConsole:
    """A general purpose Python REPL with colorizing enhancements and namespace completion.
    """

    def __init__(self,
                 namespace=None,
                 io=None,
                 ps1="Python> ",
                 ps2="..more> ",
                 history=None,
                 debug=False):
        self._ns = namespace or globals()
        self._io = io or ConsoleIO()
        self._debug = debug
        if history:
            self.history = os.path.expandvars(os.path.expanduser(history))
        else:
            self.history = None
        readline.set_history_length(1000)
        if sys.platform == "darwin":
            readline.parse_and_bind("^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        try:
            self.saveps1, self.saveps2 = sys.ps1, sys.ps2
        except AttributeError:
            self.saveps1, self.saveps2 = ">>> ", "... "
        sys.ps1, sys.ps2 = ps1, ps2
        if self.history:
            try:
                readline.read_history_file(self.history)
            except FileNotFoundError:
                pass
        self.compiler = CommandCompiler()
        # set up completer
        self._oldcompleter = readline.get_completer()
        readline.set_completer(self.complete)
        self._reset()

    def _reset(self):
        self._buffer = []

    def __del__(self):
        sys.ps1, sys.ps2 = self.saveps1, self.saveps2
        if self.history:
            readline.write_history_file(self.history)
        if self._oldcompleter:
            readline.set_completer(self._oldcompleter)

    def complete(self, text, state):
        if state == 0:
            interpreter = Interpreter(text, [self._ns])
            completions = interpreter.complete(fuzzy=False)
            self._matches = [
                text[:len(text) - c._like_name_length] + c.name_with_symbols for c in completions
            ]
        try:
            return self._matches[state]
        except IndexError:
            return None

    def runsource(self, source, filename="<repl>", symbol="single"):
        try:
            code = self.compiler(source, filename, symbol)
        except (OverflowError, SyntaxError, ValueError):
            self.showsyntaxerror(filename)
            return False

        if code is None:
            return True

        self.runcode(code)
        return False

    def runcode(self, code):
        try:
            exec(code, self._ns)
        except SystemExit:
            raise
        except:  # noqa
            if self._debug:
                ex, val, tb = sys.exc_info()
                del tb
                debugger.from_exception(val)
            else:
                self.showtraceback()

    def showsyntaxerror(self, filename=None):
        type, value, tb = sys.exc_info()
        sys.last_type = type
        sys.last_value = value
        sys.last_traceback = tb
        if filename and type is SyntaxError:
            try:
                msg, (dummy_filename, lineno, offset, line) = value.args
            except ValueError:
                pass
            else:
                value = SyntaxError(msg, (filename, lineno, offset, line))
                sys.last_value = value
        self._io.write(colors.cyan("\nSyntaxError\n"))
        lines = traceback.format_exception_only(type, value)
        self._io.write(''.join(lines))

    def print_exc(self, prefix, val):
        self._io.write("{}{}: {}\n".format(prefix, colors.red(type(val).__name__), val))
        orig = val
        while val.__context__ is not None:
            val = val.__context__
            self.print_exc(" Within: ", val)
        val = orig
        while val.__cause__ is not None:
            val = val.__cause__
            self.print_exc(" From: ", val)

    def showtraceback(self):
        _, val, tb = sys.exc_info()
        self.print_exc("", val)
        try:
            ss = traceback.extract_tb(tb)
            self._io.write("".join(ss.format()[2:]))
        finally:
            # remove references to exception objects in case this is in traceback path.
            _ = val = tb = None

    def interact(self, banner=None):
        if banner:
            self._io.write("{}\n".format(colors.white(banner)))
        more = 0
        while 1:
            try:
                if more:
                    prompt = sys.ps2
                else:
                    prompt = sys.ps1

                try:
                    line = self._io.input(prompt)
                except EOFError:
                    self._io.write("\n")
                    if self.history:
                        readline.write_history_file(self.history)
                    break
                else:
                    more = self.push(line)
            except KeyboardInterrupt:
                self._io.write(colors.red("\nKeyboardInterrupt\n"))
                self._reset()
                more = 0

    def push(self, line):
        self._buffer.append(line)
        source = "\n".join(self._buffer)
        more = self.runsource(source)
        if not more:
            self._reset()
        return more


if __name__ == "__main__":
    cons = InteractiveConsole()
    cons.interact("Test REPL banner.")
