# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
        self.initialize()

    def initialize(self):
        pass

    def finalize(self):
        pass

    def close(self):
        pass


class SoftwareRole(metaclass=abc.ABCMeta):
    def __init__(self, software):
        self._software = software
        self.initialize()

    def initialize(self):
        pass

    def finalize(self):
        pass


def get_role(classpath):
    """Get a role implementation by its path name."""
    return importlib.get_class(classpath, __name__)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
