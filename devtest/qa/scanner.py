# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Objects for finding and managing test cases from the testcases base package
namespace.
"""

from __future__ import generator_stop

import sys
import pkgutil

from .. import importlib

from .bases import TestCase, TestSuite, Scenario


def iter_module_specs(package="testcases", onerror=None):
    """Yield a ModuleSpec for all modules in the base package.
    Default is *testcases* package.
    """
    try:
        mod = importlib.import_module(package)
    except ImportError as ierr:
        if callable(onerror):
            onerror(package)
        else:
            print("The package {!r} could not be imported.".format(package),
                  file=sys.stderr)
        return
    for finder, name, ispkg in pkgutil.walk_packages(
            path=mod.__path__, prefix=mod.__name__ + '.', onerror=onerror):
        if not ispkg and "._" not in name:
            spec = finder.find_spec(name)
            yield spec


def iter_modules(package="testcases", onerror=None):
    for spec in iter_module_specs(package=package, onerror=onerror):
        mod = importlib.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except (ImportError, AttributeError) as err:
            if callable(onerror):
                onerror("{}.{}: {}".format(mod.__package__, mod.__name__, err))
            else:
                print(err, file=sys.stderr)
            continue
        yield mod


def iter_subclasses(baseclass, package="testcases", onerror=None):
    """Yield all subclasses of baseclass in provided package."""
    for mod in iter_modules(package, onerror=None):
        yield from _iter_module(mod, baseclass)


def iter_testcases(package="testcases", onerror=None):
    yield from iter_subclasses(TestCase, package=package, onerror=onerror)


def iter_testsuites(package="testcases", onerror=None):
    yield from iter_subclasses(TestSuite, package=package, onerror=onerror)


def iter_scenarios(package="testcases", onerror=None):
    yield from iter_subclasses(Scenario, package=package, onerror=onerror)


def iter_any_class(package="testcases", onerror=None):
    yield from iter_subclasses((TestCase, TestSuite, Scenario),
                               package=package, onerror=onerror)


def iter_all_runnables(package="testcases", onerror=None):
    for mod in iter_modules(package=package, onerror=onerror):
        if hasattr(mod, "run"):
            yield mod
        yield from _iter_module(mod, (TestCase, Scenario))


def _iter_module(mod, baseclass):
    for name in dir(mod):
        if not name.startswith("_"):
            obj = getattr(mod, name)
            if type(obj) is type and issubclass(obj, baseclass):
                yield obj


def _test(argv):
    for spec in iter_module_specs():
        print(spec)
    print("name:", spec.name)
    print("parent:", spec.parent)
    print("origin:", spec.origin)
    print("cached:", spec.cached)
    print("has_location:", spec.has_location)

    tc = None
    for tc in iter_all_runnables("testcases"):
        print(tc)
    return tc


if __name__ == "__main__":
    tc = _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
