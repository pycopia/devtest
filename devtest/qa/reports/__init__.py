
"""Base class and factory functions for reporting objects.
"""

import locale
import pkgutil

from devtest import importlib
from devtest.qa.signals import *  # noqa
from devtest.core.exceptions import ReportFindError


class BaseReport:
    """Base report that all run-time reports should inherit from."""

    def initialize(self, config=None):
        test_start.connect(self.on_test_start)
        test_version.connect(self.on_test_version)
        test_end.connect(self.on_test_end)
        test_passed.connect(self.on_test_passed)
        test_incomplete.connect(self.on_test_incomplete)
        test_failure.connect(self.on_test_failure)
        test_expected_failure.connect(self.on_test_expected_failure)
        test_abort.connect(self.on_test_abort)
        test_info.connect(self.on_test_info)
        test_warning.connect(self.on_test_warning)
        test_diagnostic.connect(self.on_test_diagnostic)
        test_data.connect(self.on_test_data)
        test_arguments.connect(self.on_test_arguments)
        suite_start.connect(self.on_suite_start)
        suite_end.connect(self.on_suite_end)
        suite_summary.connect(self.on_suite_summary)
        suite_info.connect(self.on_suite_info)
        run_start.connect(self.on_run_start)
        run_end.connect(self.on_run_end)
        run_error.connect(self.on_run_error)
        report_testbed.connect(self.on_report_testbed)
        report_comment.connect(self.on_run_comment)
        target_build.connect(self.on_dut_version)
        logdir_location.connect(self.on_logdir_location)

    def finalize(self):
        test_start.disconnect(self.on_test_start)
        test_version.disconnect(self.on_test_version)
        test_end.disconnect(self.on_test_end)
        test_passed.disconnect(self.on_test_passed)
        test_incomplete.disconnect(self.on_test_incomplete)
        test_failure.disconnect(self.on_test_failure)
        test_expected_failure.disconnect(self.on_test_expected_failure)
        test_abort.disconnect(self.on_test_abort)
        test_info.disconnect(self.on_test_info)
        test_warning.disconnect(self.on_test_warning)
        test_diagnostic.disconnect(self.on_test_diagnostic)
        test_data.disconnect(self.on_test_data)
        test_arguments.disconnect(self.on_test_arguments)
        suite_start.disconnect(self.on_suite_start)
        suite_end.disconnect(self.on_suite_end)
        suite_summary.disconnect(self.on_suite_summary)
        suite_info.disconnect(self.on_suite_info)
        run_start.disconnect(self.on_run_start)
        run_end.disconnect(self.on_run_end)
        run_error.disconnect(self.on_run_error)
        report_testbed.disconnect(self.on_report_testbed)
        report_comment.disconnect(self.on_run_comment)
        target_build.disconnect(self.on_dut_version)
        logdir_location.disconnect(self.on_logdir_location)

    def on_test_start(self, testcase, time=None):
        pass

    def on_test_end(self, testcase, time=None):
        pass

    def on_test_passed(self, testcase, message=None):
        pass

    def on_test_incomplete(self, testcase, message=None):
        pass

    def on_test_failure(self, testcase, message=None):
        pass

    def on_test_expected_failure(self, testcase, message=None):
        pass

    def on_test_abort(self, testcase, message=None):
        pass

    def on_test_info(self, testcase, message=None):
        pass

    def on_test_warning(self, testcase, message=None):
        pass

    def on_test_diagnostic(self, testcase, message=None):
        pass

    def on_test_data(self, testcase, data=None):
        pass

    def on_test_arguments(self, testcase, arguments=None):
        pass

    def on_suite_start(self, suite, time=None):
        pass

    def on_suite_end(self, suite, time=None):
        pass

    def on_suite_summary(self, suite, result=None):
        pass

    def on_suite_info(self, testplan, message=None):
        pass

    def on_run_start(self, runner, time=None):
        pass

    def on_run_end(self, runner, time=None):
        pass

    def on_run_error(self, runner, exc=None):
        pass

    def on_run_comment(self, runner, message=None):
        pass

    def on_report_testbed(self, runner, testbed=None):
        pass

    def on_dut_version(self, device, build=None, variant=None):
        pass

    def on_test_version(self, testcase, version=None):
        pass

    def on_logdir_location(self, runner, path=None):
        pass


class NullReport(BaseReport):
    """A report that emits nothing."""
    pass


class StackedReport(list, BaseReport):
    """A report that contains a collection of other reports.
    """

    def initialize(self, config=None):
        for rpt in self:
            rpt.initialize(config=config)

    def finalize(self):
        for rpt in self:
            rpt.finalize()


def get_report(rname):
    """Report object factory.

    Return a report object given a name, as a string. The name may be a comma
    separated list of names in which case a "stacked" report will be returned.
    The names should match the name of a module found in this subpackage. The
    first report object found in it will be returned. If the name contains a dot
    as separator then the last component is a class name that will be used
    (explicit selection of the module class from any module).

    Some names are special. The name *null* returns a NullReport, it emits
    nothing. You can also use *default* for the default report that writes to
    the terminal.
    """
    if "," in rname:
        rnames = [name.strip() for name in rname.split(",")]
        rpt = StackedReport()
        for subname in rnames:
            subrpt = get_report(subname)
            rpt.append(subrpt)
        return rpt
    elif rname.startswith("default"):
        from . import default
        if locale.getpreferredencoding() == 'UTF-8':
            return default.DefaultReportUnicode()
        else:
            return default.DefaultReport()
    elif rname.startswith("null"):
        return NullReport()
    elif "." in rname:
        try:
            robj = importlib.get_class(rname)
            return robj()
        except ImportError as ierr:
            raise ReportFindError(
                "No report class {!r} found.".format(rname)) from ierr
    else:
        # name is taken as a module name in this package. First subclass of
        # BaseReport found in there is used.
        try:
            mod = importlib.import_module("." + rname, package=__name__)
        except ImportError:
            raise ReportFindError(
                "No report module {!r} found.".format(rname)) from None
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, BaseReport):
                if obj is BaseReport:
                    continue
                return obj()
        raise ReportFindError(
            "No report found in report module {!r}.".format(rname))


def _report_finder():
    for finder, name, ispkg in pkgutil.iter_modules(__path__,
                                                    prefix=__name__ + "."):
        if not ispkg:
            mod = importlib.import_module(name)
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and issubclass(obj, BaseReport):
                    if obj is BaseReport:
                        continue
                    yield mod.__name__ + "." + obj.__name__
                    break


def get_report_list():
    return [rptmod for rptmod in _report_finder()]


def _test(argv):
    rpt = get_report("default")
    print(rpt)
    print("These reports are defined:")
    for rptname in get_report_list():
        print(rptname)


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
