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

"""Runner for use with Jupyter notebooks.
"""

from devtest import config
from devtest import options
from devtest.db import controllers
from devtest.qa import bases
from devtest.qa import runner
from devtest.qa import loader
from devtest.qa import scanner

import ipywidgets as widgets
from IPython import display


ModuleType = type(config)


def find_runnables(include=None, exclude=None):
    testlist = []
    for obj in scanner.iter_all_runnables(include=include, exclude=exclude):
        if type(obj) is ModuleType:
            testlist.append(obj.__name__)
        elif issubclass(obj, bases.TestCase):
            testlist.append("{}.{}".format(obj.__module__, obj.__name__))
        elif issubclass(obj, bases.Scenario):
            testlist.append("{}.{}".format(obj.__module__, obj.__name__))
    return testlist


class JupyterInterface:
    """Test runner interface for Jupyter notebooks.
    """

    def __init__(self, argv=None):
        self._tblist = None
        self._runnables = None

    def show_form(self):
        controllers.connect()
        tblist = controllers.TestBedController.all(like=None)
        runnables = find_runnables(exclude="analyze")

        self._tbselect = widgets.Select(options=tblist, description="Testbed:")
        self._rselect = widgets.SelectMultiple(options=runnables,
                                               description="Runnable Objects:",
                                               layout=widgets.Layout(width="60%",
                                                                     height="120px"))

        self._run_button = widgets.Button(description="Run", tooltip="Run",
                                          icon="running", button_style="primary")
        self._run_button.on_click(self._on_run)
        self._persist_cb = widgets.Checkbox(value=False,
                                            description="Record Results",
                                            disabled=False)
        tbbox = widgets.VBox([self._tbselect, self._persist_cb])
        display.display(widgets.VBox([widgets.HBox([self._rselect, tbbox]), self._run_button]))
        self._out = widgets.Output()
        self._tblist = tblist
        self._runnables = runnables

    def select(self):
        cf = config.get_config()
        cf["testbed"] = self._tblist[self._tbselect.index].name
        if self._persist_cb.value:
            cf["reportname"] = "jupyter,database"
        else:
            cf["reportname"] = "jupyter"

        selected = []
        for idx in self._rselect.index:
            selected.append(options.OptionSet(self._runnables[idx]))
        testlist, errlist = loader.load_selections(selected)
        return cf, testlist

    def _on_run(self, b):
        self._out.clear_output()
        with self._out:
            self.run()

    @property
    def output(self):
        return self._out

    def run(self):
        widgets.register_comm_target()
        cf, testlist = self.select()
        if testlist:
            rnr = runner.TestRunner(cf)
            return rnr.runall(testlist)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
