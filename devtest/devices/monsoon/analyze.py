#!/usr/bin/env python3.6

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Support for analysis of Monsoon capture data.
"""

from devtest import json

import numpy as np


def read_metadata(filename):
    return json.load(filename)


def read_data(filename, metadata=None):
    """Read a binary file as written by the FileHandler and convert it to
    columns.
    """
    data = np.fromfile(filename, dtype=np.double)
    data.shape = (-1, 5)
    return data.transpose()


def load(metadatafile):
    pass

if __name__ == "__main__":
    pass

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
