"""Extend the stock importlib module with extra functions.

Consolidates general purpose module finding and loading functions.

Only export the newest importlib API here.
"""

from __future__ import annotations

from importlib import import_module
from importlib import resources
from importlib.util import (find_spec, module_from_spec, spec_from_loader, spec_from_file_location,
                            decode_source)
import importlib.abc
from typing import Optional, Any, Callable
# mypy: disable_error_code=attr-defined

__all__ = [
    "get_object", "get_class", "import_module", "find_spec", "module_from_spec", "spec_from_loader",
    "spec_from_file_location"
]


class ModuleInspector(importlib.abc.InspectLoader):
    """A loader that only implements get_source method.

    This allows only source inspection without execution.
    """

    def get_source(self, fullname):
        path = self.get_filename(fullname)
        try:
            source_bytes = self.get_data(path)
        except OSError as exc:
            raise ImportError('source not available through get_data()', name=fullname) from exc
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


def get_resource(basepackage: str, name: str) -> bytes:
    """Get contents of a resource file.

    The resource file must be in a subpackage named "resources" inside the named package.

    Args:
        basepackage: path name of a package namespace.
        name: name of resource inside the "resources" subpackage.
    """
    pkgname_parts = basepackage.split(".")
    pkgname_parts.append("resources")
    return resources.read_binary(".".join(pkgname_parts), name)


def get_class(modulepath: str, package: Optional[str] = None) -> Any:
    """Get a class object given a full Python path name.
    """
    obj = _get_obj(modulepath, package)
    if not issubclass(obj, object):
        raise ImportError("Item addressed is not a class object.")
    return obj


def get_callable(modulepath: str, package: Optional[str] = None) -> Callable:
    """Get a callable object given a full path name.
    """
    obj = _get_obj(modulepath, package)
    if not callable(obj):
        raise ImportError("Item addressed is not a callable object.")
    return obj


def find_package_paths(pkgname: str):
    """Yield all the source base paths for a package. The package may be a
    namespace package. This will reveal all the file-system locations of a
    namespace package.
    """
    spec = find_spec(pkgname)
    if spec:
        if spec.has_location:
            assert spec.loader is not None
            if spec.loader.is_package(pkgname):
                mod = import_module(spec.name)
                for p in mod.__path__:
                    yield p
