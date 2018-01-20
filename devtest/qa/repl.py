"""
Custom REPL copied from code module and modified.
"""

import sys
import readline
import traceback
from codeop import CommandCompiler

try:
    from jedi.utils import setup_readline
    setup_readline()
except ImportError:
    import rlcompleter  # noqa

from devtest.ui.simpleui import ConsoleIO
from devtest.textutils import colors


class InteractiveConsole:

    def __init__(self, namespace=None, io=None, ps1="Python> ", ps2="more> ",
                 history=None):
        self._ns = namespace or globals()
        self._io = io or ConsoleIO()
        self.history = history
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
        self._reset()

    def _reset(self):
        self._buffer = []

    def __del__(self):
        sys.ps1, sys.ps2 = self.saveps1, self.saveps2
        if self.history:
            readline.write_history_file(self.history)

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

    def print_exc(self, name, val):
        self._io.write("{}: {}\n".format(colors.red(name), val))
        if val.__cause__ is not None:
            self.print_exc("Because: {}".format(val.__cause__.__class__.__name__), val.__cause__)

    def showtraceback(self):
        ex, val, tb = sys.exc_info()
        self.print_exc(ex.__name__, val)
        try:
            ss = traceback.extract_tb(tb)
            self._io.write("".join(ss.format()[2:]))
        finally:
            ex = val = tb = None

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


def _test(argv):
    cons = InteractiveConsole()
    cons.interact("A banner.")


if __name__ == "__main__":
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
