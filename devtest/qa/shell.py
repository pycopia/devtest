# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shell UI (command) for test framework.

Collects options and arguments from the command line, then invokes the
TestRunner with the selected runnable objects.

Runnable objects are TestCase, Scenario, or module objects that have a `run`
function or method.

A simple, interactive picker can also be used to choose runnable objects and
testbeds.

The run callable should have the following signature.

    run(config, testbed, UI)

Where:
    `config` is a nested config.ConfigDict object.
    `testbed` is a db.testbeds.TestBedRuntime object.
    `UI` is a devtest.ui.simpleui.SimpleUserInterface object.
"""

import sys

from .. import config
from .. import options
from .. import debugger
from ..textutils import colors
from . import loader
from . import runner
from . import scanner
from . import bases


ModuleType = type(sys)


USAGE = r"""devtester [options] [-c <configfile>]
    [<globalconfig>...] [<testname> [<testconfig>]] ...

Select and run tests or test suites from the command line.

The globalconfig and testconfig arguments are in long option format
(e.g. --arg1=val1).

Options:

    -h  - This help.
    -l  - List available tests.
    -v  - Be more verbose, if possible.
    -c  - Additional YAML config file to merge into configuration.
    -C  - Show configuration, after overrides applied.
    -S  - Show information about selected test case (source) and exit.
    -L  - List available testbeds.
    -R  - List available reports that may be used to direct output to.
    -d  - Debug mode. Enter a debugger if a test has an error other
          than a failure condition.
    -D  - Debug framework mode. Enter a debugger on uncaught exception within runner.
    -E  - Show stderr during run. By default stderr is redirected to a file.
          Also enables logging to stderr.
    -K  - Keep any temporary files or directories that modules might create.
    -P  - Interactively pick a test to run.
    -T  - Interactively pick a testbed to run on.
    -r <x> - Repeat targeted test object this many times. Default 1.

Example:

  devtester -d --reportname=default --testbed=mytestbed --global1=globalarg \
          testcases.mytest --mytestopt=arg

That will run a test in debug mode (-d), select the report named "default",
select the (pre-defined) test bed named "mytestbed", set global option "global1"
to "globalarg, and select the testcase "testcases.mytest. That test will get its
own option in the `options` attribute with key "mytestopt", and argument "arg".

Use the `-l` option to print a list of runnable objects there are found when
scanned.
"""  # noqa


class UsageError(Exception):
    pass


class ShellInterface:
    """Implement the shell command interface."""

    def __init__(self, argv):
        self.debug_framework = False
        self.pick_tests = False
        debug = 0
        verbose = 0
        repeat = 1
        extra_config = None
        do_list = False
        do_list_testbeds = False
        do_pick_testbed = False
        do_list_reports = False
        do_show_config = False
        do_show_testcase = False
        show_stderr = False
        keep = False
        try:
            opts, self.arguments = options.getopt(argv, "h?dDEKvlLRSCc:r:PT")
        except options.GetoptError as geo:
            _usage(geo)
        for opt, optarg in opts:
            if opt in "h?":
                _usage()
            elif opt == "d":
                debug += 1
            elif opt == "D":
                self.debug_framework = True
            elif opt == "v":
                verbose += 1
            elif opt == "l":
                do_list = True
            elif opt == "c":
                extra_config = optarg
            elif opt == "r":
                repeat = int(optarg)
            elif opt == "L":
                do_list_testbeds = True
            elif opt == "T":
                do_pick_testbed = True
            elif opt == "R":
                do_list_reports = True
            elif opt == "C":
                do_show_config = True
            elif opt == "S":
                do_show_testcase = True
            elif opt == "E":
                show_stderr = True
            elif opt == "K":
                keep = True
            elif opt == "P":
                self.pick_tests = True

        globalargs = self.arguments.pop(0)
        self.config = cf = config.get_config(initdict=globalargs.options,
                                             _filename=extra_config)
        # Adjust the configuration with the commandline options.
        cf.flags.debug = debug
        cf.flags.verbose = verbose
        cf.flags.do_list = do_list
        cf.flags.do_list_testbeds = do_list_testbeds
        cf.flags.do_list_reports = do_list_reports
        cf.flags.do_show_config = do_show_config
        cf.flags.do_show_testcase = do_show_testcase
        cf.flags.stderr = show_stderr
        cf.flags.keep = keep
        cf.flags.repeat = max(repeat, 1)
        if do_pick_testbed:
            cf["testbed"] = pick_testbed()

    def run(self):
        if self.config.flags.do_list:
            return self.do_list()
        if self.config.flags.do_show_config:
            config.show_config(self.config)
            return
        if self.config.flags.do_list_reports:
            list_reports()
            return
        if self.config.flags.do_list_testbeds:
            list_testbeds(self.config.flags.verbose)
            return
        if not self.arguments and self.pick_tests:
            pick_tests(self.arguments)
        testlist = errlist = None
        try:
            testlist, errlist = loader.load_selections(self.arguments)
        except:  # noqa
            ex, val, tb = sys.exc_info()
            if self.debug_framework:
                debugger.post_mortem(tb)
            else:
                _print_exception(ex, val)
        if errlist:
            print("Warning: some modules could not be loaded:", file=sys.stderr)
            for errarg in errlist:
                print("  ", colors.magenta(errarg.argument), file=sys.stderr)
        if testlist:
            if self.config.flags.do_show_testcase:
                from . import displayer
                rnr = displayer.TestReporter(self.config)
                return rnr.showall(testlist)
            # One runner to run them all, one runner to find them...
            try:
                rnr = runner.TestRunner(self.config)
                return rnr.runall(testlist)
            except:  # noqa
                ex, val, tb = sys.exc_info()
                if self.debug_framework:
                    debugger.post_mortem(tb)
                else:
                    _print_exception(ex, val)
        else:
            print("Warning: nothing to run.", file=sys.stderr)

    def do_list(self):
        errlist = []

        def _onerror(err):
            errlist.append(err)

        print(colors.white("Runnable objects:"))
        for obj in scanner.iter_all_runnables(onerror=_onerror):
            if type(obj) is ModuleType:
                print("    module", colors.cyan("{}".format(obj.__name__)))
            elif issubclass(obj, bases.TestCase):
                print("      test", colors.green("{}.{}".format(
                    obj.__module__, obj.__name__)))
            elif issubclass(obj, bases.Scenario):
                print("  scenario", colors.yellow("{}.{}".format(
                    obj.__module__, obj.__name__)))
            else:
                print(colors.red("  Unknown: {!r}".format(obj)))
        if errlist:
            print("These could not be scanned:")
            for errored in errlist:
                print(colors.magenta(errored))


def list_reports():
    from devtest.qa import reports
    print("Available reports in reports module:")
    for classname in reports.get_report_list():
        print(end=" ")
        parts = classname.split(".")
        print(".".join(parts[:-2]), colors.green(parts[-2]), parts[-1], sep=".")


def list_testbeds(verbose):
    from devtest.db import models
    models.connect()
    print("Available testbeds:")
    if verbose:
        for tb in models.TestBed.select():
            print(" ", colors.green(tb.name))
            for te in tb.testequipment:
                print("   ", te.equipment.name, "role:", te.function.name)
    else:
        for tb in models.TestBed.get_list():
            print(" ", colors.green(tb))


def pick_testbed():
    from devtest.ui import simpleui
    from devtest.db import models
    models.connect()
    tblist = models.TestBed.get_list()
    return simpleui.choose(tblist, defidx=tblist.index("default"),
                           prompt="Choose testbed")


def pick_tests(argumentlist):
    from devtest.ui import simpleui
    testlist = ["-done-"]
    for obj in scanner.iter_all_runnables():
        if type(obj) is ModuleType:
            testlist.append(obj.__name__)
        elif issubclass(obj, bases.TestCase):
            testlist.append("{}.{}".format(obj.__module__, obj.__name__))
        elif issubclass(obj, bases.Scenario):
            testlist.append("{}.{}".format(obj.__module__, obj.__name__))
    while 1:
        sel = simpleui.choose(testlist,
                              prompt="Choose testable (-done- value to end)")
        if sel == "-done-":
            break
        optset = options.OptionSet(sel)
        argumentlist.append(optset)


def _print_exception(ex, val):
    print("Error: {}: {}".format(ex.__name__, val), file=sys.stderr)
    orig = val
    while val.__context__ is not None:
        val = val.__context__
        print(" Within: {}: {}".format(val.__class__.__name__, val), file=sys.stderr)
    val = orig
    while val.__cause__ is not None:
        val = val.__cause__
        print("   From: {}: {}".format(val.__class__.__name__, val), file=sys.stderr)


def _usage(err=None):
    if err is not None:
        print(err, file=sys.stderr)
    print(USAGE, file=sys.stderr)
    raise UsageError()


def devtester(argv):
    """Main function for shell interface."""
    try:
        intf = ShellInterface(argv)
        return intf.run()
    except UsageError:
        return 2


if __name__ == "__main__":
    devtester(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
