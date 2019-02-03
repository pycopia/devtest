# python3

"""A report that writes test results to the database.
"""


from devtest.db import models
from devtest.core.constants import TestResultType, TestResult
from devtest.db.importers import testcases as testcases_importer

from . import BaseReport


class DatabaseReport(BaseReport):

    def initialize(self, config=None):
        super().initialize(config=config)
        self._tci = testcases_importer.TestcasesImporter()
        models.connect()
        self._resultstack = []

    def finalize(self):
        super().finalize()
        models.database.commit()

    def on_run_start(self, runner, time=None):
        runresult = models.TestResults(starttime=time,
                                       resulttype=TestResultType.TestRunSummary)
        runresult.save()
        self._resultstack.append(runresult)

    def on_run_end(self, runner, time=None):
        runresult = self._resultstack.pop()
        runresult.result = TestResult.NA
        runresult.endtime = time
        runresult.save()
        assert len(self._resultstack) == 0

    def on_run_arguments(self, runner, message=None):
        self._resultstack[0].arguments = message

    def on_logdir_location(self, runner, path=None):
        self._resultstack[0].resultslocation = path

    def on_suite_start(self, suite, time=None):
        sr = models.TestResults(starttime=time,
                                resulttype=TestResultType.TestSuite)
        sr.parent = self._resultstack[-1]
        sr.testsuite = self._tci.process_testsuite(
            type(suite), name=suite.test_name, doc=suite.doc)
        sr.save()
        self._resultstack.append(sr)

    def on_suite_end(self, suite, time=None):
        sr = self._resultstack[-1]
        sr.endtime = time

    def on_suite_summary(self, suite, result=None):
        sr = self._resultstack.pop()
        sr.result = result
        sr.save()

    def on_suite_info(self, suite, message=None):
        _add_diagnostic(self._resultstack[-1], message)

    def on_dut_version(self, device, build=None, variant=None):
        self._resultstack[0].dutbuild = "{} ({})".format(build, variant)

    def on_run_comment(self, runner, message=None):
        self._resultstack[0].note = message

    def on_test_start(self, testcase, time=None):
        tr = models.TestResults(starttime=time,
                                resulttype=TestResultType.Test)
        tr.parent = self._resultstack[-1]
        tr.testcase = self._tci.process_testcase(type(testcase), name=testcase.test_name)
        tr.save()
        self._resultstack.append(tr)

    def on_test_version(self, testcase, version=None):
        self._resultstack[-1].testversion = version

    def on_test_end(self, testcase, time=None):
        tr = self._resultstack.pop()
        tr.endtime = time
        tr.save()

    def on_test_passed(self, testcase, message=None):
        tr = self._resultstack[-1]
        tr.result = TestResult.PASSED
        tr.note = message

    def on_test_incomplete(self, testcase, message=None):
        tr = self._resultstack[-1]
        tr.result = TestResult.INCOMPLETE
        _add_diagnostic(tr, message)

    def on_test_failure(self, testcase, message=None):
        tr = self._resultstack[-1]
        tr.result = TestResult.FAILED
        _add_diagnostic(tr, message)

    def on_test_expected_failure(self, testcase, message=None):
        tr = self._resultstack[-1]
        tr.result = TestResult.EXPECTED_FAIL
        _add_diagnostic(tr, message)

    def on_test_abort(self, testcase, message=None):
        tr = self._resultstack[-1]
        tr.result = TestResult.ABORTED
        _add_diagnostic(tr, message)

    def on_test_diagnostic(self, testcase, message=None):
        _add_diagnostic(self._resultstack[-1], message)

    def on_test_data(self, testcase, data=None):
        olddata = self._resultstack[-1].data
        if olddata is not None:
            if isinstance(olddata, list):
                olddata.append(data)
                data = olddata
            else:
                data = [olddata, data]
        self._resultstack[-1].data = data

    def on_test_arguments(self, testcase, arguments=None):
        if arguments:
            self._resultstack[-1].arguments = arguments

    def on_report_testbed(self, runner, testbed=None):
        self._resultstack[-1].testbed = testbed


def _add_diagnostic(obj, message):
    if message:
        if obj.diagnostic:
            obj.diagnostic += "\n"
            obj.diagnostic += message
        else:
            obj.diagnostic = message


def _test(argv):
    rpt = DatabaseReport()
    rpt.initialize()
    rpt.finalize()


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
