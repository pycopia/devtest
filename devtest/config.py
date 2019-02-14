# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration object and factory function.

Based on the confit YAML configuration module.

http://confit.readthedocs.org/en/latest/

Config files are merged together from various sources. The default values are
embedded here in the file config_default.yaml. User's may override, or set
additional values, by placing a "config.yaml" file in one of the following
directoryies.

- ~/.config/devtest/
"""

import sys
import os
from copy import deepcopy
from collections import ChainMap

from devtest.third_party import confit


_CONFIG = None  # singleton instance.


class AttributeChainMap(ChainMap):
    """Top-level configuration object.

    Used by most of the rest of the framework.
    A subclass of ChainMap, it allows chaining other configurations later.
    """
    def __init__(self, *maps):
        self.__dict__["maps"] = list(maps) or [{}]

    def __getattr__(self, name):
        try:
            return self.__getitem__(name)
        except KeyError:
            raise AttributeError(
                "AttributeChainMap: No attribute or key {!r}".format(name)) from None

    def __setattr__(self, name, val):
        self.__setitem__(name, val)

    def __delattr__(self, name):
        self.__delitem__(name)

    # Behave like defaultdict, returning empty ConfigDict by default.
    def __missing__(self, key):
        value = ConfigDict()
        self.__setitem__(key, value)
        return value


class ConfigDict(dict):
    """Configuration Dictionary.

    Provides both attribute style and normal mapping style syntax to access
    mapping values.

    Also features "reaching into" sub-containers using a dot-delimited syntax
    for the key:

        Python3> cf = config.get_config()
        Python3> print(cf.flags.debug)
        0
        Python3> cf["flags.debug"]
        0
    """
    def __init__(self, *args, **kwargs):
        self.__dict__["_depth"] = kwargs.pop("_depth", 0)
        dict.__init__(self, *args, **kwargs)

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, dict.__repr__(self))

    def __str__(self):
        getitem = dict.__getitem__
        s = ["{}{{".format(" " * self._depth)]
        sortedkeys = sorted(self.keys())
        for key in sortedkeys:
            val = getitem(self, key)
            s.append("{}{} = {}".format("  " * self._depth, key, val))
        s.append("{}}}".format(" " * self._depth))
        return "\n".join(s)

    def __setitem__(self, name, value):
        d, name = self._get_subtree(name)
        return dict.__setitem__(d, name, value)

    def __getitem__(self, name):
        d, name = self._get_subtree(name)
        return dict.__getitem__(d, name)

    def __delitem__(self, name):
        d, name = self._get_subtree(name)
        return dict.__delitem__(d, name)

    def _get_subtree(self, name):
        d = self
        depth = self.__dict__["_depth"]
        parts = name.split(".")
        for part in parts[:-1]:
            depth += 1
            d = d.setdefault(part, self.__class__(_depth=depth))
        return d, parts[-1]

    __setattr__ = __setitem__
    __delattr__ = __delitem__

    def __getattr__(self, name):
        try:
            return self.__getitem__(name)
        except KeyError:
            raise AttributeError("AttrDict: No attribute or key {!r}".format(name)) from None

    def copy(self):
        return self.__class__(self)

    __copy__ = copy

    # Deep copies get regular dictionaries, not new AttrDict
    def __deepcopy__(self, memo):
        new = dict()
        for key, value in self.items():
            new[key] = deepcopy(value, memo)
        return new


def get_config(initdict=None, _filename=None, **kwargs):
    """Get primary configuration.

    Returns a Configuration instance containing configuration parameters. An
    extra dictionary may be merged in with the 'initdict' parameter.  And
    finally, extra options may also be added with keyword parameters.
    """
    global _CONFIG
    if _CONFIG is None:
        cf = confit.Configuration("devtest", "devtest")
        if _filename:
            cf.set_file(_filename)
        if isinstance(initdict, dict):
            cf.add(initdict)
        cf.add(kwargs)
        _CONFIG = AttributeChainMap(cf.flatten(dclass=ConfigDict))
    return _CONFIG


def show_config(cf, _path=None):
    """Print the configuration as a list of paths and the end value.
    """
    path = _path or []
    keys = sorted(cf.keys())
    for key in keys:
        value = cf[key]
        path.append(key)
        if isinstance(value, dict):
            show_config(value, path)
        else:
            print(".".join(path), "=", repr(value))
        path.pop(-1)


def get_testcase_config(testclass):
    """Add configuration specific to a class.

    Will load YAML files that are specific to a test case class. If there is a
    YAML file in the same directory as the test case, with the same name as the
    test case, it will get a configuration with that data merged in.

    If there is a file named "config_default.yaml" in the directory then that is
    also merged in, for all tests contained there. The `confit` module handles
    that part.

    Arguments:
        testclass: a test class object (not instance).
    """
    modname = testclass.__module__
    newcf = confit.Configuration(modname.split(".")[0], modname)
    mod = sys.modules[modname]
    filename = os.path.join(os.path.dirname(mod.__file__),
                            testclass.__name__ + ".yaml")
    if os.path.exists(filename):
        newcf.set_file(filename)
    cf = get_config()
    return cf.new_child(newcf.flatten(dclass=ConfigDict))


def _test(argv):
    global _CONFIG
    # Simple test gets and shows config.
    cf = get_config()
    cf.flags.debug = 1
    cf.flags.verbose = 1
    assert cf.flags.debug == 1
    _CONFIG = None
    cf = get_config(initdict={"initkey": "initvalue"})
    assert cf.get("initkey", "") == "initvalue"


if __name__ == "__main__":
    _test([])

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
