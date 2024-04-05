# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utils module for miscellaneous general functions.

Small functions can go right in here. Larger collections are found in modules
contained in the package.
"""

ViewType = type({}.keys())


def flatten(alist):
    """Flatten a list of lists or views.
    """
    rv = []
    for val in alist:
        if isinstance(val, (list, tuple)):
            rv.extend(flatten(val))
        elif isinstance(val, ViewType):
            rv.extend(flatten(list(val)))
        else:
            rv.append(val)
    return rv
