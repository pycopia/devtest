"""Support for finding test cases from a base package
namespace. The default namespace package is called "testcases".
"""

from __future__ import generator_stop

import re
import sys
import pkgutil

from .. import importlib

from .bases import TestCase, TestSuite, Scenario

__all__ = [
    'iter_module_specs', 'iter_modules', 'iter_subclasses', 'iter_testcases', 'iter_testsuites',
    'iter_scenarios', 'iter_any_class', 'iter_all_runnables', 'iter_module_classes'
]


class _DummyExcluder:

    def search(self, string):
        return False


class _DummyIncluder:

    def search(self, string):
        return True


class _ListMatcher:

    def __init__(self, relist):
        self._relist = [re.compile(el) for el in relist]

    def search(self, string):
        return any(myre.search(string) for myre in self._relist)


def iter_module_specs(package="testcases", onerror=None, include=None, exclude=None):
    """Yield a ModuleSpec for all modules in the base package.
    Default is *testcases* package.

    Args:
        package: str, name of base package to start scanning from.
        onerror: optional callable that will be called on ImportError. Callable
                 will be called with subpackage name.
        include: str or compiled regular expression. Names to explicity include.
        exclude: str or list of str (REs). Any matches will be excluded from modules yielded.
                 Optional.
    """
    if include:
        if isinstance(include, str):
            include = re.compile(include)
        if not hasattr(include, "search"):
            raise ValueError("Include option should be string or RE object.")
    else:
        include = _DummyIncluder()

    if exclude:
        if isinstance(exclude, str):
            exclude = re.compile(exclude)
        elif isinstance(exclude, list):
            exclude = _ListMatcher(exclude)
        if not hasattr(exclude, "search"):
            raise ValueError("Exclude option should be string or RE object.")
    else:
        exclude = _DummyExcluder()

    try:
        mod = importlib.import_module(package)
    except ImportError:
        if callable(onerror):
            onerror(package)
        else:
            print("The package {!r} could not be imported.".format(package), file=sys.stderr)
        return
    for finder, name, ispkg in pkgutil.walk_packages(path=mod.__path__,
                                                     prefix=mod.__name__ + '.',
                                                     onerror=onerror):
        if not ispkg and "._" not in name and include.search(name) and not exclude.search(name):
            spec = finder.find_spec(name)
            yield spec


def iter_modules(package="testcases", onerror=None, include=None, exclude=None):
    for spec in iter_module_specs(package=package,
                                  onerror=onerror,
                                  include=include,
                                  exclude=exclude):
        mod = importlib.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except (ImportError, AttributeError) as err:
            if callable(onerror):
                onerror("{}: {}".format(mod.__name__, err))
            else:
                print(err, file=sys.stderr)
            continue
        yield mod


def iter_subclasses(baseclass, package="testcases", onerror=None, include=None, exclude=None):
    """Yield all subclasses of baseclass in provided package."""
    for mod in iter_modules(package, onerror=onerror, include=include, exclude=exclude):
        yield from iter_module_classes(mod, baseclass)


def iter_testcases(package="testcases", onerror=None):
    yield from iter_subclasses(TestCase, package=package, onerror=onerror)


def iter_testsuites(package="testcases", onerror=None):
    yield from iter_subclasses(TestSuite, package=package, onerror=onerror)


def iter_scenarios(package="testcases", onerror=None):
    yield from iter_subclasses(Scenario, package=package, onerror=onerror)


def iter_any_class(package="testcases", onerror=None):
    yield from iter_subclasses((TestCase, TestSuite, Scenario), package=package, onerror=onerror)


def iter_all_runnables(package="testcases", onerror=None, include=None, exclude=None):
    for mod in iter_modules(package=package, onerror=onerror, include=include, exclude=exclude):
        if hasattr(mod, "run"):
            yield mod
        yield from iter_module_classes(mod, (TestCase, Scenario))


def iter_module_classes(mod, baseclass):
    for name in dir(mod):
        if not name.startswith("_"):
            obj = getattr(mod, name)
            if type(obj) is type and issubclass(obj, baseclass):
                yield obj


def _test(argv):
    spec = None
    for spec in iter_module_specs():
        print(spec)
    if spec is not None:
        print("name:", spec.name)
        print("parent:", spec.parent)
        print("origin:", spec.origin)
        print("cached:", spec.cached)
        print("has_location:", spec.has_location)

    print("Runnables:")
    tc = None
    for tc in iter_all_runnables("testcases", exclude=["resources"]):
        print(tc)
    return tc


if __name__ == "__main__":
    tc = _test(sys.argv)
