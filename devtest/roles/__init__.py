"""
Implementations of abstract role interfaces. Test cases can get objects from
here via the testbed attribute.
"""

from __future__ import generator_stop

import abc
from .. import importlib


class BaseRole(metaclass=abc.ABCMeta):
    def __init__(self, equipment):
        self._equipment = equipment


    def initialize(self):
        pass


    def finalize(self):
        pass


class SoftwareRole(metaclass=abc.ABCMeta):
    def __init__(self, software):
        self._software = software


def get_role(classpath):
    """Get a role implementation by its path name."""
    return importlib.get_class(classpath, __name__)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
