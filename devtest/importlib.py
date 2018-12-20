# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Extend the stock importlib module with extra functions.

Consolidates general purpose module finding and loading functions.

Only export the newest importlib API here.
"""

from __future__ import generator_stop

import os
from importlib import import_module
from importlib.util import (find_spec, module_from_spec, spec_from_loader,
                            spec_from_file_location, decode_source)
import importlib.abc


__all__ = ["get_object", "get_class", "import_module", "find_spec",
           "module_from_spec", "spec_from_loader", "spec_from_file_location"]


class ModuleInspector(importlib.abc.InspectLoader):
    """A loader that only implements get_source method.

    This allows only source inspection without execution.
    """
    def get_source(self, fullname):
        path = self.get_filename(fullname)
        try:
            source_bytes = self.get_data(path)
        except OSError as exc:
            raise ImportError('source not available through get_data()',
                              name=fullname) from exc
        return decode_source(source_bytes)


def get_object(name):
    """Get either a class or module.
    """
    try:
        return import_module(name)
    except ImportError:
        return get_class(name)


def _get_obj(modulepath, package):
    if "." in modulepath:
        modulename, classname = modulepath.rsplit(".", 1)
    else:
        raise ImportError("Item addressed is not a full path.")
    mod = import_module(modulename, package=package)
    return getattr(mod, classname)


def get_class(modulepath, package=None):
    """Get a class object given a full Python path name.
    """
    obj = _get_obj(modulepath, package)
    if not issubclass(obj, object):
        raise ImportError("Item addressed is not a class object.")
    return obj


def get_callable(modulepath, package=None):
    """Get a callable object given a full path name.
    """
    obj = _get_obj(modulepath, package)
    if not callable(obj):
        raise ImportError("Item addressed is not a callable object.")
    return obj


def find_package_paths(pkgname):
    """Yield all the source base paths for a package. The package may be a
    namespace package. This will reveal all the file-system locations of a
    namespace package.
    """
    try:
        spec = find_spec(pkgname)
    except ValueError:  # Work around bug here.
        mod = sys.modules[pkgname]
        for p in mod.__path__:
            yield p
        return
    if spec:
        if spec.has_location:
            if spec.loader.is_package(pkgname):
                mod = import_module(spec.name)
                for p in mod.__path__:
                    yield p


def find_package_path(pkgname):
    """Find the directory path to the package with the given package name.

    May raise ImportError if the package can not be found.
    """
    spec = find_spec(pkgname)
    if spec:
        if spec.has_location:
            if spec.loader.is_package(pkgname):
                return os.path.dirname(spec.origin)
            else:
                raise ImportError("{!r} is not a package.".format(pkgname))
        else:
            raise ImportError("pkg {!r} not found.".format(pkgname))
    else:
        raise ImportError("No module or package name {!r}.".format(pkgname))


def _test(argv):
    scls = get_class("socket.socket")
    print(scls, type(scls))


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
