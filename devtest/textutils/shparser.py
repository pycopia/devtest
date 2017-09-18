"""
A parser for splitting a simple POSIX shell syntax.

- Does not need a stream or file object.
- Expands environment variables.
- Feed parser design, may be used to feed from other sources.
- Allows backslash escaped special characters.
"""

import sys
import os

from .fsm import FiniteStateMachine, ANY

_SPECIAL = {"r":"\r", "n":"\n", "t":"\t", "b":"\b"}

class ShellParser:
    """Simple shell-like syntax feed parser."""
    VARNAME = r'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_?'  # noqa

    def __init__(self, callback=None):
        self._cb = callback or self._default_cb
        self.reset()
        self._init()

    def _default_cb(self, argv):
        self._argv = argv

    def reset(self):
        self.arg_list = []
        self._buf = ""
        self._argv = None

    def feedline(self, text):
        self.feed(text)
        return self.feed("\n")

    def feed(self, text):
        text = self._buf + text
        i = 0
        for c in text:
            self._fsm.process(c)
            while self._fsm.stack:
                self._fsm.process(self._fsm.pop())
            i += 1
        if self._fsm.current_state: # non-zero, stuff left
            self._buf = text[i:]
        return self._fsm.current_state

    def _init(self):
        f = FiniteStateMachine(0)
        f.arg = ""
        f.add_default_transition(self._error, 0)
        # normal text for args
        f.add_transition(ANY, 0, self._addtext, 0)
        f.add_transition_list(" \t", 0, self._wordbreak, 0)
        f.add_transition_list(";\n", 0, self._doit, 0)
        # slash escapes
        f.add_transition("\\", 0, None, 1)
        f.add_transition("\\", 3, None, 6)
        f.add_transition(ANY, 1, self._slashescape, 0)
        f.add_transition(ANY, 6, self._slashescape, 3)
        # environment variables
        f.add_transition("$", 0, self._startvar, 7)
        f.add_transition("{", 7, self._vartext, 9)
        f.add_transition_list(self.VARNAME, 7, self._vartext, 7)
        f.add_transition(ANY, 7, self._endvar, 0)
        f.add_transition("}", 9, self._endvarbrace, 0)
        f.add_transition(ANY, 9, self._vartext, 9)
        # vars in singlequote are not expanded
        f.add_transition("$", 3, self._startvar, 8)
        f.add_transition("{", 8, self._vartext, 10)
        f.add_transition_list(self.VARNAME, 8, self._vartext, 8)
        f.add_transition(ANY, 8, self._endvar, 3)
        f.add_transition("}", 10, self._endvarbrace, 3)
        f.add_transition(ANY, 10, self._vartext, 10)
        # quotes allow embedding word breaks and such.
        # Single quotes can quote double quotes, and vice versa.
        f.add_transition("'", 0, None, 2)
        f.add_transition("'", 2, self._singlequote, 0)
        f.add_transition(ANY, 2, self._addtext, 2)
        f.add_transition('"', 0, None, 3)
        f.add_transition('"', 3, self._doublequote, 0)
        f.add_transition(ANY, 3, self._addtext, 3)
        self._fsm = f

    def _startvar(self, c, fsm):
        fsm.varname = c

    def _vartext(self, c, fsm):
        fsm.varname += c

    def _endvar(self, c, fsm):
        fsm.push(c)
        fsm.arg += os.environ.get(fsm.varname[1:], "")

    def _endvarbrace(self, c, fsm):
        fsm.varname += c
        fsm.arg += os.environ.get(fsm.varname[2:-1], "")

    def _error(self, input_symbol, fsm):
        print('Syntax error: {}\n{!r}'.format(input_symbol, fsm.stack),
              file=sys.stderr)
        fsm.reset()

    def _addtext(self, c, fsm):
        fsm.arg += c

    def _wordbreak(self, c, fsm):
        if fsm.arg:
            self.arg_list.append(fsm.arg)
            fsm.arg = ''

    def _slashescape(self, c, fsm):
        fsm.arg += _SPECIAL.get(c, c)

    def _singlequote(self, c, fsm):
        self.arg_list.append(fsm.arg)
        fsm.arg = ''

    def _doublequote(self, c, fsm):
        self.arg_list.append(fsm.arg)
        fsm.arg = ''

    def _doit(self, c, fsm):
        if fsm.arg:
            self.arg_list.append(fsm.arg)
            fsm.arg = ''
        self._cb(self.arg_list)
        self.arg_list = []


class CommandSplitter:
    """Adapt the feed parser to a string splitter."""
    def __init__(self):
        self._argv = None
        self._cmd_parser = ShellParser(self._cb)

    def _cb(self, argv):
        self._argv = argv

    def feedline(self, text):
        self._cmd_parser.feedline(text)
        return self._argv


def get_command_splitter():
    """Return a callable that will split shell-syntax strings into a list of
    tokens.
    """
    _cmd_splitter = CommandSplitter()
    return _cmd_splitter.feedline


def split(line):
    return CommandSplitter().feedline(line)


def _test(argv):
    TEST = r'command args "with quotes" and $PATH or with curlies\n \$USER=${USER}'
    line = " ".join(argv[1:]) if len(argv) > 1 else TEST
    parts = split(line)
    if line.startswith(r'command'):  # our test
        assert len(parts) == 9
        assert parts[0] == "command"
        assert parts[1] == "args"
        assert parts[2] == "with quotes"
        assert parts[4][0] != "$"
        assert parts[-1].endswith(os.environ["USER"])
        assert parts[-2].endswith('\n')
    else:
        print(parts)


if __name__ == '__main__':
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
