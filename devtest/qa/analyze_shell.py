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

"""Shell interface to Analyzer modules.
"""

import sys

from devtest import config
from devtest import options
from devtest import debugger
from devtest.textutils import colors

from . import scanner
from . import loader


ModuleType = type(sys)


def iter_all_analyzers(package="testcases", onerror=None, include=None, exclude=None):
    for mod in scanner.iter_modules(package=package, onerror=onerror,
                                    include=include, exclude=exclude):
        if hasattr(mod, "run"):
            yield mod


class UsageError(Exception):
    pass


class ShellInterface:
    """Call analyzer modules for test cases.

    Usage:
        devtestanalyze [-hdl] <module> [<module_long_option>...]
            [<module> [<module_long_options>...]]...

    Options:
        -h  - This help.
        -d  - Debug on.
        -l  - List available analyzer modules.
    """

    def __init__(self, argv):
        debug = 0
        extra_config = None
        do_list = False

        try:
            opts, self.arguments = options.getopt(argv, "h?dlc:")
        except options.GetoptError as geo:
            _usage(geo)
        for opt, optarg in opts:
            if opt in "h?":
                _usage()
            elif opt == "d":
                debug += 1
            elif opt == "l":
                do_list = True
            elif opt == "c":
                extra_config = optarg
        globalargs = self.arguments.pop(0)
        self.config = cf = config.get_config(initdict=globalargs.options,
                                             _filename=extra_config)
        cf.flags.debug = debug
        cf.flags.do_list = do_list

    def run(self):
        if self.config.flags.do_list:
            return do_list()

        runlist = errlist = None
        try:
            runlist, errlist = loader.load_selections(self.arguments)
        except:  # noqa
            exclass, exc, tb = sys.exc_info()
            if self.config.flags.debug:
                debugger.from_exception(exc)
            else:
                _print_exception(exc)
        if not runlist:
            _usage("Nothing to run.")
        for module in runlist:
            try:
                module.run()
            except:  # noqa
                exclass, exc, tb = sys.exc_info()
                if self.config.flags.debug:
                    debugger.from_exception(exc)
                else:
                    _print_exception(exc)
                return 70  # EX_SOFTWARE


def do_list():
    errlist = []

    def _onerror(err):
        errlist.append(err)

    print(colors.white("Analyzer objects:"))
    for obj in iter_all_analyzers(onerror=_onerror, include="analyze"):
        if type(obj) is ModuleType:
            print("    module", colors.cyan("{}".format(obj.__name__)))
        else:
            print(colors.red("  Unknown: {!r}".format(obj)))
    if errlist:
        print("These could not be scanned:")
        for errored in errlist:
            print("  ", errored)


def _usage(err=None):
    if err is not None:
        print(err, file=sys.stderr)
    print(ShellInterface.__doc__, file=sys.stderr)
    raise UsageError()


def _print_exception(exc):
    print("Error: {}: {}".format(exc.__class__.__name__, exc), file=sys.stderr)
    orig = exc
    while exc.__context__ is not None:
        exc = exc.__context__
        print(" Within: {}: {}".format(exc.__class__.__name__, exc), file=sys.stderr)
    exc = orig
    while exc.__cause__ is not None:
        exc = exc.__cause__
        print("   From: {}: {}".format(exc.__class__.__name__, exc), file=sys.stderr)


def devtestanalyze(argv):
    """Main function for shell interface."""
    try:
        intf = ShellInterface(argv)
        return intf.run()
    except UsageError:
        return 64  # EX_USAGE


if __name__ == "__main__":
    devtestanalyze(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
