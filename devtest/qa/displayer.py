"""
Report on test case source code.
"""

import inspect

from pygments.lexers import python
from pygments.lexers import markup
from pygments.formatters import terminal
from pygments import highlight

from devtest import logging

from . import bases

ModuleType = type(bases)


class TestReporter:
    """Runs test objects.

    Handled running objects, initializing reports, testbeds, services, etc.
    then runs tests and cleans up afterwards.
    """
    def __init__(self, cfg):
        self.config = cfg
        self._pylexer = python.Python3Lexer()
        self._doclexer = markup.RstLexer()
        self._formatter = terminal.TerminalFormatter()

    def showall(self, testlist):
        for obj in testlist:
            objecttype = type(obj)
            if objecttype is type:
                if issubclass(obj, bases.TestCase):
                    self.show_testcase(obj)
                elif issubclass(obj, bases.Scenario):
                    self.show_scenario(obj)
                elif issubclass(obj, bases.TestSuite):
                    self.show_suite(obj)
            elif objecttype is ModuleType and hasattr(obj, "run"):
                self.show_module(obj)
            else:
                logging.warn("{!r} is not a runnable object.".format(obj))

    def show_testcase(self, testcase):
        name = testcase.__qualname__
        head = "\n".join([name, "="*len(name)])
        doc = inspect.cleandoc(inspect.getdoc(testcase))
        print(highlight(head + "\n" + doc, self._doclexer, self._formatter))
        if self.config.flags.verbose:
            print(highlight(inspect.getsource(testcase.execute), self._pylexer,
                  self._formatter))

    def show_scenario(self, scenario):
        name = scenario.__qualname__
        head = "\n".join([name, "="*len(name)])
        doc = inspect.cleandoc(inspect.getdoc(scenario))
        print(highlight(head + "\n" + doc, self._doclexer, self._formatter))
        if self.config.flags.verbose:
            print(highlight(inspect.getsource(scenario.get_suite), self._pylexer,
                  self._formatter))

    def show_suite(self, suite):
        name = suite.__qualname__
        head = "\n".join([name, "="*len(name)])
        doc = inspect.cleandoc(inspect.getdoc(suite))
        print(highlight(head + "\n" + doc, self._doclexer, self._formatter))
        if self.config.flags.verbose:
            print(highlight(inspect.getsource(suite.initialize), self._pylexer,
                  self._formatter))
            print(highlight(inspect.getsource(suite.finalize), self._pylexer,
                  self._formatter))

    def show_module(self, mod):
        name = mod.__name__
        head = "\n".join([name, "="*len(name)])
        doc = inspect.cleandoc(inspect.getdoc(mod))
        print(highlight(head + "\n" + doc, self._doclexer, self._formatter))
        if self.config.flags.verbose:
            print(highlight(inspect.getsource(mod.run), self._pylexer,
                  self._formatter))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
