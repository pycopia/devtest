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
"""Output module for use when running a test session from withing Jupyter.
"""

import os
from datetime import timezone

from devtest import json

from . import BaseReport

widgets = None
display = None


class JupyterReport(BaseReport):

    def initialize(self, config=None):
        # Done this way so that ipywidgets isn't a hard dependency for the rest
        # of the framework. Jupyter has a boatload if dependencies.
        global widgets, display
        import ipywidgets as widgets
        from IPython import display
        self._logdir = "/tmp"
        widgets.register_comm_target()
        self._out = widgets.Output(layout={"width": "100%"})
        display.display(self._out)
        if config is not None:
            self._logdir = config.get("resultsdir", "/tmp")
            self.timezone = config.get("timezone", timezone.utc)
        else:
            self.timezone = timezone.utc
        super().initialize(config=config)

    def finalize(self):
        self._display_html("<hr/>")
        self._out = None
        super().finalize()

    def _display_html(self, string, time=None):
        if time is not None:
            ts = time.astimezone(self.timezone).timetz().isoformat()
            s = ('<div style="display:table;width=100%">'
                 '  <div style="display:table-row">'
                 '    <div style="display:table-cell;width:80%">{}</div>'
                 '    <div style="display:table-cell;color:blue;text-align:right">{}</div>'
                 '  </div></div>').format(string, ts)
        else:
            s = string
        self._out.append_display_data(display.HTML(s))

    def on_run_start(self, runner, time=None):
        self._display_html(
            '<div style="font-size:120%;font-weight:bold">'
            'Runner start</div>&nbsp;', time=time)

    def on_run_end(self, runner, time=None):
        self._display_html("Runner end", time=time)

    def on_suite_start(self, suite, time=None):
        self._display_html('<div style="font-size:110%;font-weight:bold">'
                           'Start Test Suite <em>{}</em></div>'.format(suite.test_name),
                           time=time)

    def on_suite_end(self, suite, time=None):
        self._display_html('End Test Suite <em>{}</em><br/>'.format(suite.test_name), time=time)

    def on_test_start(self, testcase, time=None):
        name = testcase.test_name
        self._display_html('<div style="font-weight:bold">'
                           'Start Test Case <em>{}</em></div>'.format(name),
                           time=time)

    def on_test_end(self, testcase, time=None):
        name = testcase.test_name
        self._display_html('End Test Case <em>{}</em>'.format(name), time=time)

    def on_test_passed(self, testcase, message=None):
        self._display_html('<span style="color:green">PASSED</span>: {!s}'.format(message))

    def on_test_incomplete(self, testcase, message=None):
        self._display_html('<span style="color:yellow">INCOMPLETE</span>: {!s}'.format(message))

    def on_test_failure(self, testcase, message=None):
        self._display_html('<span style="color:red">FAILED</span>: {!s}'.format(message))

    def on_test_expected_failure(self, testcase, message=None):
        self._display_html('<span style="color:magenta">EXPECTED FAIL</span>: {!s}'.format(message))

    def on_test_abort(self, testcase, message=None):
        self._display_html('<span style="color:yellow">ABORTED</span>: {!s}'.format(message))

    def on_test_info(self, testcase, message=None):
        self._display_html('{}<br/>'.format(message))

    def on_test_warning(self, testcase, message=None):
        self._display_html('Warning: <span style="color:pink">{}</span><br/>'.format(message))

    def on_test_diagnostic(self, testcase, message=None):
        self._display_html('Diagnostic: <span style="color:magenta">{}</span><br/>'.format(message))

    def on_test_arguments(self, testcase, arguments=None):
        if arguments:
            self._display_html(
                'Arguments: <span style="color:cyan">{}</span><br/>'.format(arguments))

    def on_suite_info(self, suite, message=None):
        self._display_html('{}<br/>'.format(message))

    def on_run_error(self, runner, exc=None):
        self._display_html('<div class="error">Run error: {}</div>'.format(exc))

    def on_dut_version(self, device, build=None, variant=None):
        self._display_html("DUT version: {!s} ({})<br/>".format(build, variant))

    def on_logdir_location(self, runner, path=None):
        self._logdir = path
        relpath = os.sep.join(path.split(os.sep)[-2:])
        self._display_html('Results location: '
                           '<a href="{path}/" target="_blank">{path}/</a>'.format(path=relpath))
        # Note that this doesn't actually work in the browser. It's just for
        # display purposes for now.

    def on_test_data(self, testcase, data=None):
        # If the same test is run multiple times, add new data to top-level
        # list. Make a new top-level list if required.
        fname = "{}_data.json".format(testcase.test_name.replace(".", "_"))
        fpath = os.path.join(self._logdir, fname)
        olddata = None
        if os.path.exists(fpath):
            with open(fpath) as fo:
                olddata = json.load(fo)
            if isinstance(olddata, list):
                olddata.append(data)
                data = olddata
            else:
                data = [olddata, data]
        with open(fpath, "w") as fo:
            json.dump(data, fo)
        self._display_html("Data: {} {!r}<br/>".format("added to" if olddata else "available in",
                                                       fname))


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
