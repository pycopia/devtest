# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Default report used when running tests.

Supports simple, colored reports for both unicode and non-unicode terminals.

Also servers as usage example of TestCase signals.
"""

import sys
import os
from datetime import timezone

from devtest import json

from . import BaseReport

WIDTH, LINES = os.get_terminal_size()

RESET = "\x1b[0m"  # aka NORMAL

ITALIC_ON = "\x1b[3m"
ITALIC_OFF = "\x1b[23m"

UNDERLINE_ON = "\x1b[4m"
UNDERLINE_OFF = "\x1b[24m"

INVERSE_ON = "\x1b[7m"
INVERSE_OFF = "\x1b[27m"

RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
GREY = "\x1b[37m"

LT_RED = "\x1b[31;01m"
LT_GREEN = "\x1b[32;01m"
LT_YELLOW = "\x1b[33;01m"
LT_BLUE = "\x1b[34;01m"
LT_MAGENTA = "\x1b[35;01m"
LT_CYAN = "\x1b[36;01m"
WHITE = "\x1b[01m"  # aka INTENSE or BRIGHT,

RED_BACK = "\x1b[41m"
GREEN_BACK = "\x1b[42m"
YELLOW_BACK = "\x1b[43m"
BLUE_BACK = "\x1b[44m"
MAGENTA_BACK = "\x1b[45m"
CYAN_BACK = "\x1b[46m"
WHITE_BACK = "\x1b[47m"

#                 UL  hor   vert  UR  LL   LR
_BOXCHARS = {1: ['╔', '═', '║', '╗', '╚', '╝'],
             2: ['┏', '━', '┃', '┓', '┗', '┛'],
             3: ['┌', '─', '│', '┐', '└', '┘']}


_BOXCHARS_A = {1: ['+', '=', '|', '+', '+', '+'],
               2: ['+', '-', '|', '+', '+', '+'],
               3: ['+', '+', '|', '+', '+', '+']}


def white(text):
    return WHITE + text + RESET


def inverse(text):
    return INVERSE_ON + text + INVERSE_OFF


def green(text):
    return GREEN + text + RESET


def red(text):
    return RED + text + RESET


def blue(text):
    return BLUE + text + RESET


def yellow(text):
    return YELLOW + text + RESET


def cyan(text):
    return CYAN + text + RESET


def magenta(text):
    return MAGENTA + text + RESET


def lt_red(text):
    return LT_RED + text + RESET


def inverse_red(text):
    return INVERSE_ON + RED + text + RESET + INVERSE_OFF


class DefaultReport(BaseReport):

    def initialize(self, config=None):
        self._file = sys.stdout
        self._logdir = "/tmp"
        if config is not None:
            self._logdir = config.get("resultsdir", "/tmp")
            self.timezone = config.get("timezone", timezone.utc)
        else:
            self.timezone = timezone.utc
        super().initialize(config=config)

    def finalize(self):
        super(DefaultReport, self).finalize()
        self._file = None

    def on_test_start(self, testcase, time=None):
        name = testcase.test_name
        ts = time.astimezone(self.timezone).timetz().isoformat()
        nw = WIDTH - len(ts) - 1
        print("\n{W}{0:{width}s} {B}{1}{R}".format(name, ts,
              width=nw, W=UNDERLINE_ON, B=BLUE, R=RESET), file=self._file)

    def on_test_end(self, testcase, time=None):
        ts = time.astimezone(self.timezone).timetz().isoformat()
        print("{U}{}{R} ended at {B}{:s}{R}".format(testcase.test_name,
              ts, B=BLUE, R=RESET, U=UNDERLINE_ON), file=self._file)

    def on_test_passed(self, testcase, message=None):
        print("{}: {!s}".format(green("PASSED"), message), file=self._file)

    def on_test_incomplete(self, testcase, message=None):
        print("{}: {!s}".format(yellow("INCOMPLETE"), message),
              file=self._file)

    def on_test_failure(self, testcase, message=None):
        print("{}: {!s}".format(red("FAILED"), message), file=self._file)

    def on_test_expected_failure(self, testcase, message=None):
        print("{}: {!s}".format(lt_red("EXPECTED FAILED"), message),
              file=self._file)

    def on_test_abort(self, testcase, message=None):
        print("{}: {!s}".format(inverse_red("ABORTED"), message),
              file=self._file)

    def on_test_info(self, testcase, message=None):
        print(" info:", message, file=self._file)

    def on_test_warning(self, testcase, message=None):
        print(yellow(" warning:"), message, file=self._file)

    def on_test_diagnostic(self, testcase, message=None):
        print(magenta("diagnostic:"), message, file=self._file)

    def on_test_arguments(self, testcase, arguments=None):
        if arguments:
            print(cyan("    arguments:"), arguments, file=self._file)

    def on_suite_start(self, testsuite, time=None):
        ts = time.astimezone(self.timezone).timetz().isoformat()
        nw = WIDTH - len(ts) - 13
        print("\nstart suite {W}{0:{width}s} {B}{1}{R}".format(
              testsuite.test_name, ts, width=nw, W=WHITE, B=BLUE, R=RESET),
              file=self._file)

    def on_suite_end(self, testsuite, time=None):
        ts = time.astimezone(self.timezone).timetz().isoformat()
        print("\nTestSuite {!r} ended at {B}{:s}{R}\n".format(
            testsuite.test_name, ts, B=BLUE, R=RESET), file=self._file)

    def on_suite_info(self, testsuite, message=None):
        print("suite info:", message, file=self._file)

    def on_run_start(self, runner, time=None):
        ts = time.astimezone(self.timezone).timetz().isoformat()
        print("Runner start at {!s}.".format(blue(ts)), file=self._file)

    def on_run_end(self, runner, time=None):
        ts = time.astimezone(self.timezone).timetz().isoformat()
        print("Runner end at {!s}.".format(blue(ts)), file=self._file)

    def on_run_error(self, runner, exc=None):
        print("Run error {}.".format(red(str(exc))), file=self._file)

    def on_dut_version(self, device, build=None, variant=None):
        print(("DUT version: {!s} ({})").format(build, variant), file=self._file)

    def on_logdir_location(self, runner, path=None):
        self._logdir = path
        print("Results location:", path, file=self._file)

    def on_test_data(self, testcase, data=None):
        fname = "{}_data.json".format(testcase.test_name)
        fpath = os.path.join(self._logdir, fname)
        with open(fpath, "a") as fo:
            json.dump(data, fo)
        print("Data written to", repr(fname), "in results location.", file=self._file)


class DefaultReportUnicode(DefaultReport):

    def on_test_passed(self, testcase, message=None):
        print("{} {!s}".format(green('✔'), message), file=self._file)

    def on_test_incomplete(self, testcase, message=None):
        print("{} {!s}".format(yellow('⁇'), message), file=self._file)

    def on_test_failure(self, testcase, message=None):
        print("{} {!s}".format(red('✘'), message), file=self._file)

    def on_test_expected_failure(self, testcase, message=None):
        print("{} {!s}".format(cyan('✘'), message), file=self._file)

    def on_test_abort(self, testcase, message=None):
        print("{} {!s}".format(inverse_red('‼'), message), file=self._file)

    def on_run_start(self, runner, time=None):
        UL, hor, vert, UR, LL, LR = _BOXCHARS[1]
        ts = time.astimezone(self.timezone).timetz().isoformat()
        nw = WIDTH - len(ts) - 2
        text = "Start run at {:{width}s}".format(ts, width=nw)
        tt = "{}{}{}".format(UL, hor * (len(text) + 2), UR)
        bt = "{}{}{}".format(LL, hor * (len(text) + 2), LR)
        ml = "{} {} {}".format(vert, text, vert)
        print(tt, ml, bt, sep="\n", file=self._file)

    def on_suite_start(self, testsuite, time=None):
        UL, hor, vert, UR, LL, LR = _BOXCHARS[2]
        ts = time.astimezone(self.timezone).timetz().isoformat()
        nw = WIDTH - len(ts) - 21
        tt = "{}{}{}".format(UL, hor * (WIDTH - 2), UR)
        bt = "{}{}{}".format(LL, hor * (WIDTH - 2), LR)
        ml = "{0} Start TestSuite: {1:{width}s} {B}{2}{R}{3}".format(
            vert, testsuite.test_name, ts, vert, width=nw, B=BLUE, R=RESET)
        print(tt, ml, bt, sep="\n", file=self._file)


def _get_timestring(dt, zone):
    return dt.astimezone(zone).timetz().isoformat()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
