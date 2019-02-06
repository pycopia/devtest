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

"""Support for analysis of Monsoon capture data and test result data.

Also useful when imported into IPython with pylab.
"""

import os

import numpy as np

from devtest import json
from devtest import config
from devtest.db import controllers
from devtest.devices.android import adb
from devtest.devices.monsoon import core as monsoon_core


class SampleData:
    """Monsoon sample data plus metadata.

    Attributes:
        samples: ndarray of all samples (from samplefile).
        columns: List of columns labels, in order of columns in samples.
        units: List of unit labels, in order of columns in samples.
        start_time: float of time measurement run started, unix time.
        sample_rate: int number of samples per second in samples array.
        voltage: The voltage set during measurement.
        dropped: Number of samples dropped by device.
        sample_count: number of raw data samples (includes ref and cal samples).
        measure_count: number of actual, measurement data samples.
        samplefile: name of the file where raw samples are stored.
        heading: str of column names and units suitable for printing a table.
        main_current: vector of main current samples only, and unit string.
        main_voltage: vector of main voltage readings only, and unit string.
    """

    def __init__(self, samples=None, result=None):
        self._samples = samples
        if result is not None:
            self.columns = result.columns
            self.units = result.units
            self.start_time = result.start_time
            self.sample_rate = result.sample_rate
            self.voltage = result.voltage
            self.dropped = result.dropped
            self.sample_count = result.sample_count  # total samples
            self.measure_count = result.measure_count  # samples counting for measurement
            self.samplefile = result.samplefile
        else:
            self.columns = None
            self.units = None
            self.start_time = None
            self.sample_rate = None
            self.voltage = None
            self.dropped = None
            self.sample_count = None
            self.samplefile = None

    def __str__(self):
        s = [self.heading]
        s.append(repr(self.samples))
        return "\n".join(s)

    def get_column(self, name):
        """Return column data and unit of column."""
        index = self.columns.index(name)
        return self.samples[index], self.units[index]

    def get_time_axis(self, absolute=False):
        """Create a time datapoint axis from the measure data.

        Use the measure count and sample rate from the result.
        """
        offset = self.start_time if absolute else 0.0
        times = np.arange(offset,
                          offset + (self.measure_count / self.sample_rate),
                          1.0 / self.sample_rate,
                          np.float64)
        assert len(times) == self.measure_count
        return times

    def get_xy(self, name, absolute=False):
        """Return tuple of time and column value arrays, x unit, y unit.
        """
        col, unit = self.get_column(name)
        times = self.get_time_axis(absolute=absolute)
        return times, col, "s", unit

    @property
    def samples(self):
        if self._samples is None:
            if self.samplefile:
                self._samples = SampleData.read_file(self.samplefile)
        return self._samples

    @property
    def heading(self):
        heads = ["{} ({})".format(n, u) for n, u in zip(self.columns, self.units)]
        return " | ".join(heads)

    @property
    def main_current(self):
        return self.get_column("main_current")

    @property
    def main_voltage(self):
        return self.get_column("main_voltage")


    @classmethod
    def from_result(cls, result):
        """Read result object and load samples from samplefile, and metadata.
        """
        return cls(None, result)

    @classmethod
    def from_file(cls, filename):
        """Read raw samples from a file without metadata.
        """
        data = SampleData.read_file(filename)
        return cls(data, None)

    @staticmethod
    def read_file(filename):
        """Read a binary file as written by the FileHandler and convert it to
        columns.

        Return:
            ndarray
        """
        data = np.fromfile(filename, dtype=np.double)
        data.shape = (-1, 5)
        return data.transpose()


def read_metadata(filename):
    return json.from_file(filename)


def dump_logcat(fname, tag=None):
    """Dump a binary logcat file to stdout as text.
    """
    lfr = adb.LogcatFileReader(fname)
    lfr.dump(tag=tag)


def load_data(md, _dataobjects=None):
    """Convert metadata records to known data objects.
    """
    if _dataobjects is None:
        _dataobjects = []
    if isinstance(md, list):
        for section in md:
            load_data(section, _dataobjects)
    elif isinstance(md, dict):
        fname = md.get("logfile")
        if fname:
            fname = _fix_path(fname)
            _dataobjects.append(adb.LogcatFileReader(fname))
        else:
            _dataobjects.append(md)
    elif isinstance(md, monsoon_core.MeasurementResult):
        md.samplefile = _fix_path(md.samplefile)
        _dataobjects.append(SampleData.from_result(md))
    else:
        _dataobjects.append(md)
    return _dataobjects


def _fix_path(path):
    """Fix the the logdir path, in case it was moved."""
    cf = config.get_config()
    resultsdir = os.path.expandvars(cf.resultsdir)
    if path.startswith(resultsdir):
        return path
    dirname, fname = os.path.split(path)
    origresultsdir, subdir = os.path.split(dirname)
    return os.path.join(resultsdir, subdir, fname)


def find_data_files(testcasename):
    """Find all data files as written by devtest.qa.bases.TestCase.record_data()
    and default output.

    Only those matching the testcasename.
    """
    cf = config.get_config()
    resultsdir = os.path.expandvars(cf.resultsdir)
    for dirpath, dirnames, filenames in os.walk(resultsdir):
        for fname in filenames:
            if testcasename in fname and fname.endswith("json"):
                md = read_metadata(os.path.join(dirpath, fname))
                yield md


def find_test_results(testcasename):
    """Find metadata of a test case result in the database."""
    controllers.connect()
    return [result for result in
            controllers.TestResultsController.results_for(testcasename)
            if result.data is not None]


def get_latest_samples(testcasename):
    """Get the latest sample data and logs from a test case that records samples.
    """
    sampledata = None
    logfile = None
    extra = None
    result = find_test_results(testcasename)[-1]
    for resultobj in load_data(result.data):
        if isinstance(resultobj, SampleData):
            sampledata =  resultobj
        elif isinstance(resultobj, adb.LogcatFileReader):
            logfile = resultobj
        else:
            extra = resultobj
    return result, sampledata, logfile, extra


def get_all_samples(testcasename):
    """Get all available data objects for a test.

    Returns
        List of tuples of (sampledata, logfile, extradata).
    """
    alldata = []
    for testresult in find_test_results(testcasename):
        sampledata = None
        logfile = None
        extra = None
        for resultobj in load_data(testresult.data):
            if isinstance(resultobj, SampleData):
                sampledata = resultobj
            elif isinstance(resultobj, adb.LogcatFileReader):
                logfile = resultobj
            else:
                extra = resultobj
        alldata.append((testresult, sampledata, logfile, extra))
    return alldata


if __name__ == "__main__":
    import sys
    testname = sys.argv[1]
    for data in find_data_files(testname):
        for obj in load_data(data):
            print(obj)
        print()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
