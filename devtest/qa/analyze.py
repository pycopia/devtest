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
from devtest.os import meminfo


def convert_meminfo(mi):
    return [(ts.timestamp(), meminfo.MemUsage(*memdata)) for ts, memdata in mi]


def convert_cpuinfo(cpui):
    return [(ts, cpuutil) for ts, cpuutil in cpui]


def to_memusage(analyzer, data=None, config=None):
    if isinstance(data, dict):
        meminfolist = data.get("meminfo")
        if meminfolist:
            data["meminfo"] = convert_meminfo(meminfolist)
        return data


def to_cpuinfo(analyzer, data=None, config=None):
    if isinstance(data, dict):
        ci = data.get("cpuinfo")
        if ci:
            data["cpuinfo"] = convert_cpuinfo(ci)
        return data

# Connect the general memory usage and CPU usage data to converters for
# everything.
signals.data_convert.connect(to_memusage)
signals.data_convert.connect(to_cpuinfo)


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
        self.resultslocation = os.path.expandvars(config.resultsdir)
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

    @classmethod
    def from_test_entry(cls, testcase):
        """Factory method to make Analyzer from TestCase model instance.
        """
        return cls.from_testcase(testcase.testimplementation)

    @property
    def use_local_storage(self):
        return self.config.flags.use_local

    @use_local_storage.setter
    def use_local_storage(self, yes):
        if yes:
            self.config.flags.use_local = True
        else:
            self.config.flags.use_local = False

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

    def find_latest_data(self):
        """Find latest data file for the test case.

        These are recorded as files by the default report.

        Returns:
            Python data structure as recorded by the latest test case run.
        """
        jsonname = "{}_data.json".format(self.test_name.replace(".", "_"))
        resultsdir = os.path.expandvars(self.config.resultsdir)
        latest = None
        latest_mtime = 0.0
        for dirpath, dirnames, filenames in os.walk(resultsdir):
            for fname in filenames:
                if jsonname in fname:
                    fpath = os.path.join(dirpath, fname)
                    st = os.stat(fpath)
                    if st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                        latest = fpath
        if latest is not None:
            self.resultslocation = os.path.dirname(latest)
            return json.from_file(latest)
        else:
            return None

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
        result = controllers.TestResultsController.latest_result_for(self.test_name)
        self.set_resultslocation_from_testresult(result)
        return result

    def get_latest_data(self, use_local: bool = None):
        """Get most recent data object from local store (resultsdir) or database
        depending on use_local flag.

        Args:
            use_local: (bool) override configuration flag to use local data
            storage.
        """
        if use_local is None:
            use_local = self.config.flags.use_local
        if use_local:
            return self.find_latest_data()
        else:
            result = self.latest_result()
            return result.data

    def load_data(self, data, _dataobjects=None):
        """Convert data records to registered data objects, or use as-is if not
        available.

        Registered handlers of the `data_convert` signal are given the data. If
        one can convert it or otherwise handle it it does so and returns another
        object.

        Also flattens lists of result metadata.

        Returns:
            List of converted or modified data or data structures.
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
                    break
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

    def make_filename(self, name, extension="png"):
        """Make a new file name from test case name, and supplied name.
        Adds a path in the same location as the data.

        Returns:
            Fully qualified path to a new file with test name, given name, and
            extension. The path is located in the original results location.
        """
        filename = "{}-{}.{}".format(self.test_name.replace(".", "_"), name, extension)
        return self.fix_path(os.path.join(self.resultslocation, filename))

    def set_resultslocation_from_testresult(self, testresult):
        # only root result (runner) has location
        tr = testresult
        resultslocation = testresult.resultslocation
        while resultslocation is None and tr is not None:
            tr = tr.parent
            resultslocation = tr.resultslocation
        self.resultslocation

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
