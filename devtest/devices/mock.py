# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mock device controller useful for testing and demo.
"""

from . import Controller


class MockController(Controller):

    def __init__(self, equipment):
        self._equipment = equipment
        self.name = "mock controller for {}".format(equipment.name)

    def __str__(self):
        return self.name

    def do_something(self):
        return "Did something on device."
