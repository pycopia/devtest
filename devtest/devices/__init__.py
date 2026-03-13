# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Common base for device controllers.
"""

from __future__ import generator_stop

import abc
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from devtest.db.testbeds import EquipmentRuntime
else:
    EquipmentRuntime = Any


class Controller(metaclass=abc.ABCMeta):

    def __init__(self, equipment: EquipmentRuntime):
        self._equipment = equipment
        self.initialize()

    def __del__(self):
        self.close()

    def initialize(self):
        return NotImplemented

    def reset(self):
        return NotImplemented

    def close(self):
        return NotImplemented


class Software(metaclass=abc.ABCMeta):

    def __init__(self, software):
        self._software = software
