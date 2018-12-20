# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Import all currently installed test cases from the "testcases" namespace
package into the database.
"""

import pkgutil
import inspect


from docutils import core as docutils_core
from docutils import utils
from docutils import io
from docutils.readers import doctree

from peewee import fn

from devtest import importlib
from devtest.qa import bases

from .. import models


def find_testcase_modules():
    tcmod = importlib.import_module("testcases")
    for finder, name, ispkg in pkgutil.walk_packages(tcmod.__path__,
                                                     prefix="testcases."):
        mod = importlib.import_module(name)
        yield mod


def parts_from_doctree(document):
    reader = doctree.Reader(parser_name='null')
    pub = docutils_core.Publisher(reader, None, None,
                                  source=io.DocTreeInput(document),
                                  destination_class=io.StringOutput)
    pub.set_writer("html_plain")
    pub.process_programmatic_settings(None, None, None)
    pub.set_destination(None, None)
    pub.publish(enable_exit_status=False)
    return pub.writer.parts


def get_rendered_sections(doctree):
    """Return a dict with section name keys and HTML rendered values."""
    parts = {}
    for node in doctree.children:
        nodeids = node["ids"]
        if nodeids:
            nodeid = nodeids[0]
            tempdoc = utils.new_document(None, doctree.settings)
            tempdoc.append(node)
            sbody = parts_from_doctree(tempdoc)["body"]
            parts[nodeid] = sbody
    return parts


def plain_doc(input_string):
    overrides = {'doctitle_xform': False,
                 'initial_header_level': 2}
    parts = docutils_core.publish_parts(
        source=input_string, source_path=None, destination_path=None,
        writer_name="html_plain", settings_overrides=overrides)
    return parts["body"]


class TestcasesImporter:
    """Imports the entire set of currently installed test cases.
    """
    def __init__(self, force=False):
        self.force = force

    def run(self, argv):
        self.force = "-f" in argv
        models.connect()
        for mod in find_testcase_modules():
            with models.database.transaction():
                self.process_module(mod)

    def process_module(self, mod):
        for objname in dir(mod):
            obj = getattr(mod, objname)
            if isinstance(obj, type):
                if issubclass(obj, bases.TestCase):
                    self.process_testcase(obj)
                elif issubclass(obj, bases.TestSuite):
                    self.process_testsuite(obj)
                elif issubclass(obj, bases.Scenario):
                    self.process_scenario(obj)

    def process_testcase(self, testcaseclass, update=False, name=None):
        update = update or self.force
        TC = models.TestCases
        impl = "{}.{}".format(testcaseclass.__module__, testcaseclass.__name__)
        name = name or impl.replace("testcases.", "")
        # Don't import submodules that start with underscores.
        if "._" in impl:
            return
        exists = TC.select().where(TC.name == name).exists()
        if exists and not update:
            return TC.select().where(TC.name == name).get()
        doc = inspect.cleandoc(testcaseclass.__doc__ or impl)
        if not doc:
            doc = name
        kwargs = {}
        doctree = docutils_core.publish_doctree(doc)
        parts = get_rendered_sections(doctree)
        for section_id, colname in (("purpose", "purpose"),
                                    ("pass-criteria", "passcriteria"),
                                    ("start-condition", "startcondition"),
                                    ("end-condition", "endcondition"),
                                    ("procedure", "procedure")):
            kwargs[colname] = parts.get(section_id)
        # handle non-template simple docstrings. They are assumed to be the
        # purpose.
        if not kwargs["purpose"]:
            kwargs["purpose"] = plain_doc(doc)
        kwargs["purpose_search"] = fn.to_tsvector(kwargs.get("purpose"))
        if exists:
            q = TC.update(**kwargs).where(TC.name == name)
            q.execute()
        else:
            kwargs["name"] = name
            kwargs["testimplementation"] = impl
            return TC.create(**kwargs)

    def process_testsuite(self, suiteclass, update=False, name=None, doc=None):
        update = update or self.force
        MODEL = models.TestSuites
        impl = "{}.{}".format(suiteclass.__module__, suiteclass.__name__)
        name = name or impl.replace("testcases.", "")
        if "._" in impl:
            return
        exists = MODEL.select().where(MODEL.name == name).exists()
        if exists and not update:
            return MODEL.select().where(MODEL.name == name).get()
        kwargs = {}
        doc = inspect.cleandoc(doc or suiteclass.__doc__ or name)
        kwargs["purpose"] = plain_doc(doc)
        kwargs["search_purpose"] = fn.to_tsvector(doc)
        kwargs["suiteimplementation"] = impl
        if exists:
            q = MODEL.update(**kwargs).where(MODEL.name == name)
            q.execute()
        else:
            kwargs["name"] = name
            return MODEL.create(**kwargs)

    def process_scenario(self, scenarioclass, update=False):
        update = update or self.force
        MODEL = models.Scenario
        impl = "{}.{}".format(scenarioclass.__module__, scenarioclass.__name__)
        if "._" in impl:
            return
        exists = MODEL.select().where(MODEL.implementation == impl).exists()
        if exists and not update:
            return
        doc = inspect.cleandoc(scenarioclass.__doc__ or impl)
        # Don't import classes that don't have documentation.
        if not doc:
            return
        kwargs = {}
        kwargs["name"] = impl.replace("testcases.", "")
        kwargs["purpose"] = plain_doc(doc)
        kwargs["purpose_search"] = fn.to_tsvector(doc)
        if exists:
            q = MODEL.update(**kwargs).where(MODEL.implementation == impl)
            q.execute()
        else:
            kwargs["implementation"] = impl
            MODEL.create(**kwargs)


def main(argv):
    tci = TestcasesImporter()
    tci.run(argv)


if __name__ == "__main__":
    import sys
    main(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
