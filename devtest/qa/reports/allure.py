# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create a report file for the Allure package.

For Allure, a "test" is a top level object, or a "run" to devtest.  The "steps" are the test cases.
Suites a collections of tests, or steps, that become a higher-order step. Allure allows for nesting,
so a "step" may be a suite or a test case.
"""

import pathlib
import inspect
import shutil
import tempfile

from docutils import core as docutils_core
import allure_commons
from allure_commons import model2
from allure_commons import lifecycle
from allure_commons import logger
from allure_commons import types as allure_types
from allure_commons import utils

from devtest import json
from devtest.os import procutils
from devtest.os import process
from devtest.core.constants import TestResult
from devtest.db.importers import testcases as testcases_importer

from . import BaseReport

_STATUS_MAP = {
    TestResult.NA: model2.Status.BROKEN,
    TestResult.PASSED: model2.Status.PASSED,
    TestResult.FAILED: model2.Status.FAILED,
    TestResult.INCOMPLETE: model2.Status.BROKEN,
    TestResult.SKIPPED: model2.Status.SKIPPED,
    TestResult.EXPECTED_FAIL: model2.Status.FAILED,
    TestResult.ABORTED: model2.Status.SKIPPED,
}


def _get_description(testcase):
    doc = inspect.cleandoc(testcase.__class__.__doc__)
    if not doc:
        return {}
    doctree = docutils_core.publish_doctree(doc)
    sections = testcases_importer.get_rendered_sections(doctree)
    return sections


class AllureReport(BaseReport):
    """A report that writes a report directory that is used as input to the Allure builder.
    """

    def initialize(self, config):
        super().initialize(config)
        self._logdir = pathlib.Path("/tmp").resolve()  # may be updated by runner later.
        self._properties = {}
        self._tci = testcases_importer.TestcasesImporter()
        self._tmpdir = tempfile.TemporaryDirectory(prefix="allure")
        self.logger = logger.AllureFileLogger(self._tmpdir.name)
        self.lifecycle = lifecycle.AllureLifecycle()
        allure_commons.plugin_manager.register(self.logger)

    def finalize(self):
        super().finalize()
        if self._properties:
            with open(self._tmpdir.name + "/environment.properties", "w") as fo:
                for key, value in self._properties.items():
                    fo.write(f"{key} = {value}\n")
        allure_commons.plugin_manager.unregister(plugin=self.logger)
        shutil.move(self._tmpdir.name, self._allure_results)
        self._tmpdir.cleanup()
        alluretool = procutils.which("allure")
        if alluretool:
            process.call(f"{alluretool} awesome --single-file --cwd {self._logdir} "
                         f"-o {self._logdir / 'allure-report'}")
        del self._tmpdir
        del self._logdir
        del self._tci
        del self.logger
        del self.lifecycle

    def on_test_start(self, testcase, time=None):
        docparts = _get_description(testcase)
        with self.lifecycle.schedule_test_case() as test_result:
            test_result.name = testcase.test_name
            test_result.start = _get_timestamp(time)
            test_result.fullName = testcase.OPTIONS.implementation
            test_result.descriptionHtml = docparts.get("purpose")
            test_result.preconditionHtml = docparts.get("start-condition")
            test_result.expectedResultHtml = docparts.get("pass-criteria")
            # test_result.labels.append(model2.Label(name="framework", value="devtest"))
        with self.lifecycle.update_container() as container:
            container.children.append(test_result.uuid)

    def on_test_end(self, testcase, time=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.stop = _get_timestamp(time)
        self.lifecycle.write_test_case()

    def on_test_arguments(self, testcase, arguments=None):
        if not arguments:
            return
        params = []
        argv = [part.strip() for part in arguments.split(",")]
        for argi, arg in enumerate(argv):
            if "=" in arg:
                name, _, value = arg.partition("=")
                params.append(model2.Parameter(name=name, value=value, excluded=False,
                                               mode="default"))
            else:
                params.append(model2.Parameter(name=f"arg{argi}", value=arg, excluded=False,
                                               mode="default"))
        with self.lifecycle.update_test_case() as test_result:
            test_result.parameters = params

    def on_test_passed(self, testcase, message=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.status = _STATUS_MAP[TestResult.PASSED]
            test_result.statusDetails = model2.StatusDetails(message=message)

    def on_test_incomplete(self, testcase, message=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.status = _STATUS_MAP[TestResult.INCOMPLETE]
            test_result.statusDetails = model2.StatusDetails(known=False, message=message)

    def on_test_failure(self, testcase, message=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.status = _STATUS_MAP[TestResult.FAILED]
            test_result.statusDetails = model2.StatusDetails(known=False, message=message)

    def on_test_expected_failure(self, testcase, message=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.status = _STATUS_MAP[TestResult.FAILED]
            test_result.statusDetails = model2.StatusDetails(known=True, message=message)

    def on_test_abort(self, testcase, message=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.status = _STATUS_MAP[TestResult.ABORTED]
            test_result.statusDetails = model2.StatusDetails(message=message)

    def on_test_info(self, testcase, message=None):
        pass

    def on_test_warning(self, testcase, message=None):
        pass

    def on_test_diagnostic(self, testcase, message=None):
        self.lifecycle.attach_data(utils.uuid4(), message, name="diagnostic",
                                   attachment_type=allure_types.AttachmentType.TEXT)

    def on_test_data(self, testcase, data=None):
        message = json.dumps(data)
        self.lifecycle.attach_data(utils.uuid4(), message, name="data",
                                   attachment_type=allure_types.AttachmentType.JSON)

    def on_test_version(self, testcase, version=None):
        with self.lifecycle.update_test_case() as test_result:
            test_result.labels.append(model2.Label(name="testversion", value=version))

    def on_suite_start(self, suite, time=None):
        docparts = _get_description(suite)
        with self.lifecycle.start_container() as container:
            container.name = suite.test_name
            container.start = _get_timestamp(time)
            container.fullName = suite.implementation
            container.descriptionHtml = docparts.get("purpose")

    def on_suite_end(self, suite, time=None):
        with self.lifecycle.start_container() as container:
            container.stop = _get_timestamp(time)
        self.lifecycle.write_container()

    def on_suite_summary(self, suite, result=None):
        with self.lifecycle.update_container() as container:
            container.status = _STATUS_MAP[result]

    def on_suite_info(self, testplan, message=None):
        pass

    def on_run_start(self, runner, time=None):
        self._properties["runstart"] = time.isoformat()

    def on_run_end(self, runner, time=None):
        self._properties["runend"] = time.isoformat()

    def on_run_error(self, runner, exc=None):
        self._properties["runerror"] = str(exc)

    def on_run_comment(self, runner, message=None):
        if message:
            self._properties["comment"] = str(message)

    def on_report_testbed(self, runner, testbed=None):
        self._properties["testbed"] = str(testbed.name)

    def on_dut_version(self, device, build=None, variant=None):
        self._properties["dutversion"] = f"dut_version: {build!s} ({variant})"

    def on_logdir_location(self, runner, path=None):
        self._logdir = pathlib.Path(path).resolve()
        alluredir = self._logdir / "allure-results"
        self._allure_results = alluredir


def _get_timestamp(time):
    # Allure seems to want milliseconds, but spec doesn't specify.
    return round(time.timestamp() * 1000.0)
