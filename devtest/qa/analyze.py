#!/usr/bin/env python3.6

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Basic support for analysis of data produced by test cases.
"""

import os

from devtest import json
from devtest import config
from devtest import importlib
from devtest.db import controllers
from devtest.qa import signals
from devtest.qa import bases


class Analyzer:
    """Common base class for data analyzers.

    Provides a type to inspect.

    Attributes:
        testcase: a TestCase subclass with options set.
        config: A configuration that includes the test case configuration.
    """

    optionslist = None  # loader may set instance options

    def __init__(self, testcase, config):
        self.test_name = testcase.OPTIONS.test_name
        self.config = config
        self.options = self.optionslist.pop(0) if self.optionslist else {}

    @classmethod
    def from_testcase(cls, testcase):
        """Factory method to make Analyzer from TestCase subclass.

        Args:
            testcase: str or TestCase class object. If str it should be a full
            path to class object, which will be imported.
        """
        if isinstance(testcase, str):
            testcase = importlib.get_class(testcase)
        if type(testcase) is type and issubclass(testcase, bases.TestCase):
            testcase.set_test_options()
        else:
            raise ValueError("Need a TestCase subclass or name of one.")
        cf = config.get_testcase_config(testcase)
        return cls(testcase, cf)

    def find_test_data_files(self):
        """Find all data files as written by devtest.qa.bases.TestCase.record_data()
        and default output.

        These are recorded using the default report, into a subdirectory of the
        `resultsdir` configuration item.

        Only those matching the testcase name, modifed to file name as report
        writer does.

        Yields:
            Python data structure as recorded by the test case.
        """
        jsonname = "{}_data.json".format(self.test_name.replace(".", "_"))
        resultsdir = os.path.expandvars(self.config.resultsdir)
        for dirpath, dirnames, filenames in os.walk(resultsdir):
            for fname in filenames:
                if jsonname in fname:
                    md = json.from_file(os.path.join(dirpath, fname))
                    yield md

    def find_test_results(self):
        """Find test result records for a test case.

        These are recorded using the `database` reportname.

        Returns:
            List of `devtest.db.models.TestResults` objects, but only those that
            have data attached.
        """
        controllers.connect()
        return [result for result in
                controllers.TestResultsController.results_for(self.test_name)
                if result.data is not None]

    def latest_result(self):
        """Fetch latest test result from database for this test case."""
        controllers.connect()
        return controllers.TestResultsController.latest_result_for(self.test_name)

    def load_data(self, data, _dataobjects=None):
        """Convert data records to registered data objects, or use as-is if not
        available.

        Also flattens lists of result metadata.
        """
        if _dataobjects is None:
            _dataobjects = []
        if isinstance(data, list):
            for section in data:
                self.load_data(section, _dataobjects)
        else:
            for receiver, response in signals.data_convert.send(self,
                                                                data=data,
                                                                config=self.config):
                if response is not None:
                    _dataobjects.append(response)
            else:
                _dataobjects.append(data)
        return _dataobjects

    def fix_path(self, path):
        """Fix the resultsdir path, in case it was moved.

        Data converters that want to read files from resultsdir should call
        this.

        Args:
            path: str, path from a test result record.

        Returns:
            possibly modified path, adjusting for differences in the `resultsdir`
            configuration item.
        """
        resultsdir = os.path.expandvars(self.config.resultsdir)
        if path.startswith(resultsdir):
            return path
        dirname, fname = os.path.split(path)
        origresultsdir, subdir = os.path.split(dirname)
        return os.path.join(resultsdir, subdir, fname)

    def make_filename(self, testresult, extension="png"):
        # only root result (runner) has location
        tr = testresult
        resultslocation = testresult.resultslocation
        while resultslocation is None and tr is not None:
            tr = tr.parent
            resultslocation = tr.resultslocation
        filename = "{}-{:%Y%m%d%H%M%S.%f}.{}".format(
                testresult.testcase.name.replace(".", "_"),
                testresult.starttime, extension)
        return self.fix_path(os.path.join(resultslocation, filename))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
