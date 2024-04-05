"""Main test runner for running any runnable target.
"""

import sys
import os
import signal
from datetime import datetime, timezone

import pytz
from devtest import logging

from .. import importlib
from .. import services
from .. import debugger
from ..ui import ptui
from ..core.constants import TestResult

from . import bases
from . import reports
from ..db import testbeds
from ..core.exceptions import TestRunnerError, ReportFindError, TestRunAbort
from .signals import (run_start, run_end, run_error, report_testbed, report_comment, report_final,
                      logdir_location)

ModuleType = type(os)


class TestRunner:
    """Runs test objects.

    Handled running objects, initializing reports, testbeds, services, etc.
    then runs tests and cleans up afterwards.
    """

    def __init__(self, cfg):
        self.config = cfg
        self._testbed = None
        self._origfd = None
        if tmpsuitename := cfg.get("suite"):
            self._tempsuite = importlib.get_object(tmpsuitename)
            if not issubclass(self._tempsuite, bases.TestSuite):
                raise ValueError("The suite config option must be a TestSuite.")
        else:
            self._tempsuite = bases.TestSuite

    @property
    def testbed(self):
        if self._testbed is None:
            cf = self.config
            testbed = testbeds.get_testbed(cf.get("testbed", "default"), debug=cf.flags.debug)
            testbed.claim(cf)  # may raise TestRunAbort
            report_testbed.send(self, testbed=testbed._testbed)
            self._testbed = testbed
        return self._testbed

    @testbed.deleter
    def testbed(self):
        if self._testbed is not None:
            self._testbed.finalize()
            self._testbed.release(self.config)
            self._testbed = None

    def runall(self, objects):
        """Main entry to run a list of runnable objects."""
        rl = []
        self.initialize()
        try:
            rl = [self.run_objects(objects) for i in range(self.config.flags.repeat)]
        except TestRunAbort as err:
            logging.exception_error("TestRunner.runall:", err)
            run_error.send(self, exc=err)
            return TestResult.ABORTED
        finally:
            self.finalize()
        return _aggregate_returned_results(rl)

    def run_objects(self, objects):
        """Invoke the `run` method on a list of mixed runnable objects.

        Arguments:
            objects:
                A list of runnable objects. A runnable object is basically
                something that has a callable attribute named "run" that takes a
                configuration, testbed, and UI object as a parameter.

        May raise TestRunnerError if an object is not runnable by this test
        runner.

        Bare TestCase classes are grouped together and run in a temporary
        TestSuite.
        """
        results = []
        testcases = []
        for obj in objects:
            objecttype = type(obj)
            if objecttype is type:
                if issubclass(obj, bases.TestCase):
                    testcases.append(obj)
                elif issubclass(obj, bases.Scenario):
                    results.append(obj.run(self.config, self.testbed, self._ui))
            elif isinstance(obj, bases.TestSuite):
                obj.run()
                results.append(obj.result)
            elif objecttype is ModuleType and hasattr(obj, "run"):
                results.append(self._run_module(obj))
            else:
                logging.warning("{!r} is not a runnable object.".format(obj))
        # Run any accumulated bare test classes.
        if testcases:
            if len(testcases) > 1:
                rv = self.run_tests(testcases)
            else:
                rv = self.run_test(testcases[0])
            results.append(rv)
        return _aggregate_returned_results(results)

    def _run_module(self, module_with_run):
        try:
            rv = module_with_run.run(self.config, self.testbed, self._ui)
        except:  # noqa
            ex, val, tb = sys.exc_info()
            run_error.send(self, exc=val)
            if self.config.flags.debug:
                debugger.post_mortem(tb)
            else:
                logging.exception_error(module_with_run.__name__, val)
            return TestResult.INCOMPLETE
        else:
            return rv

    def run_test(self, testclass, *args, **kwargs):
        """Run a test single test class with arguments.

        Runs a single test class with the provided arguments. Test class
        is placed in a temporary TestSuite.

        Arguments:
            testclass:
                A class that is a subclass of bases.TestCase. Any extra
                arguments given are passed to the `testcase()` method when it is
                invoked.

        Returns:
            The return value of the Test instance. Should be PASSED, FAILED,
            INCOMPLETE, or ABORT.
        """

        suite = self._tempsuite(self.config,
                                self.testbed,
                                self._ui,
                                name="{}Suite".format(testclass.__name__))
        suite.add_test(testclass, *args, **kwargs)
        suite.run()
        return suite.result

    def run_tests(self, testclasses):
        """Run a list of test classes.

        Runs a list of test classes. Test classes are placed in a temporary
        TestSuite.

        Arguments:
            testclasses:
                A list of classes that are subclasses of bases.TestCase.

        Returns:
            The return value of the temporary TestSuite instance.
        """

        suite = self._tempsuite(self.config, self.testbed, self._ui, name="RunTestsTempSuite")
        suite.add_tests(testclasses)
        suite.run()
        return suite.result

    def initialize(self):
        """Perform any initialization needed by the test runner.
        """
        signal.signal(signal.SIGTERM, _exitingsignal)
        signal.signal(signal.SIGHUP, _exitingsignal)
        cf = self.config
        cf.timezone = get_local_timezone()
        cf.resultsdir = os.path.expandvars(os.path.expanduser(cf.resultsdir))
        cf.username = os.environ["USER"]
        self._ui = ptui.PromptToolkitUserInterface()
        self.logger = logging.Logger("devtest", usestderr=cf.flags.stderr)
        self.initialize_report()
        cf.start_time = datetime.now(timezone.utc)
        ts = cf.start_time.strftime("%Y%m%d_%H%M%S")
        cf.logdir = os.path.join(cf.resultsdir, ts)
        if not os.path.exists(cf.logdir):
            os.makedirs(cf.logdir)
        # Initialize all service modules
        services.initialize()
        run_start.send(self, time=cf.start_time)
        comment = cf.get("comment")
        if comment:
            report_comment.send(self, message=comment)
        logdir_location.send(self, path=cf.logdir)
        # Direct our stderr to a file if stderr option (see stderr) is not set.
        if not cf.flags.stderr:
            fname = os.path.join(cf.logdir, "runner-stderr.txt")
            self._origfd = _redirect_stderr(fname)

    def initialize_report(self):
        """Initializes report.
        """
        cf = self.config
        rpt = cf.get("report")
        if rpt is None:
            reportname = cf.get("reportname", "default")
            try:
                rpt = reports.get_report(reportname)
            except ReportFindError as err:
                self.logger.error(str(err))
                raise TestRunnerError("Cannot continue without report.") from err
        if not isinstance(rpt, reports.BaseReport):
            raise TestRunnerError("A report needs to be instance of reports.BaseReport")
        rpt.initialize(config=cf)
        self.report = rpt

    def finalize(self):
        """Perform any finalization needed by the test runner.
        Sends runner end messages to report. Finalizes report.
        """
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        run_end.send(self, time=datetime.now(timezone.utc))
        if self._origfd is not None:
            _restore_stderr(self._origfd)
            self._origfd = None
        self.report.finalize()
        services.finalize()
        report_final.send(self.report)
        self.logger.close()
        del self._ui
        del self.testbed
        del self.config
        del self.report
        del self.logger


def _aggregate_returned_results(resultlist):
    resultset = {
        TestResult.PASSED: 0,
        TestResult.FAILED: 0,
        TestResult.EXPECTED_FAIL: 0,
        TestResult.INCOMPLETE: 0,
        TestResult.ABORTED: 0,
        TestResult.NA: 0,
        None: 0
    }
    for res in resultlist:
        resultset[res] += 1
    # Fail if any fail, else incomplete if any incomplete, pass only if all passed.
    if resultset[TestResult.FAILED] > 0:
        return TestResult.FAILED
    elif resultset[TestResult.INCOMPLETE] > 0:
        return TestResult.INCOMPLETE
    elif resultset[None] > 0:
        return TestResult.NA
    elif resultset[TestResult.ABORTED] > 0:
        return TestResult.ABORTED
    elif resultset[TestResult.PASSED] > 0:
        return TestResult.PASSED
    else:
        return TestResult.INCOMPLETE


def _redirect_stderr(name):
    fd = os.open(name,
                 os.O_WRONLY | os.O_TRUNC | os.O_CREAT | os.O_NOFOLLOW | os.O_SYNC,
                 mode=0o644)
    stderr_orig = os.dup(2)
    os.dup2(fd, 2)
    os.close(fd)
    return stderr_orig


def _restore_stderr(oldfd):
    sys.stderr.flush()
    os.dup2(oldfd, 2)
    os.close(oldfd)


def _exitingsignal(sig, stack):
    name = signal.strsignal(sig)
    raise SystemExit(f"Caught signal {name}({sig}), exiting.")


def get_local_timezone():
    try:
        link = os.readlink("/etc/localtime")
        tzname = "/".join(link.split("/")[-2:])
    except OSError:
        tzname = open("/etc/timezone").read().strip()
    return pytz.timezone(tzname)
