# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Likely, the original license is PSF.

"""Custom REPL copied from code module and modified.
"""

import sys
import readline
import traceback
import rlcompleter  # noqa
from codeop import CommandCompiler

from devtest.ui.simpleui import ConsoleIO
from devtest.textutils import colors


class InteractiveConsole:

    def __init__(self, namespace=None, io=None, ps1="Python> ", ps2="..more> ",
                 history=None):
        self._ns = namespace or globals()
        self._io = io or ConsoleIO()
        self.history = history
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
        ex, val, tb = sys.exc_info()
        self.print_exc("", val)
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


if __name__ == "__main__":
    cons = InteractiveConsole()
    cons.interact("Test REPL banner.")

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
