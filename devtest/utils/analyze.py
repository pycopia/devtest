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

"""Support for analysis of test result data.

Also useful when imported into IPython with pylab.
"""

import os

from devtest import json
from devtest import config
from devtest.db import controllers
from devtest.devices.android import logcat
from devtest.devices.monsoon import core as monsoon_core
from devtest.devices.monsoon import analyze as monsoon_analyze


def read_metadata(filename):
    return json.from_file(filename)


def dump_logcat(fname, tag=None):
    """Dump a binary logcat file to stdout as text.
    """
    lfr = logcat.LogcatFileReader(fname)
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
            _dataobjects.append(logcat.LogcatFileReader(fname))
        else:
            _dataobjects.append(md)
    elif isinstance(md, monsoon_core.MeasurementResult):
        md.samplefile = _fix_path(md.samplefile)
        _dataobjects.append(monsoon_analyze.SampleData.from_result(md))
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

    Only those matching the testcasename, modifed to file name as report writer
    does.
    """
    cf = config.get_config()
    if testcasename.startswith("testcases."):  # framework strips of "testcases" name
        testcasename = testcasename[len("testcases."):]
    jsonname = "{}_data.json".format(testcasename.replace(".", "_"))
    resultsdir = os.path.expandvars(cf.resultsdir)
    for dirpath, dirnames, filenames in os.walk(resultsdir):
        for fname in filenames:
            if jsonname in fname:
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
        if isinstance(resultobj, monsoon_analyze.SampleData):
            sampledata = resultobj
        elif isinstance(resultobj, logcat.LogcatFileReader):
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
            if isinstance(resultobj, monsoon_analyze.SampleData):
                sampledata = resultobj
            elif isinstance(resultobj, logcat.LogcatFileReader):
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
