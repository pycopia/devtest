#!/usr/bin/env python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for devtest.core.types.
"""

from devtest.core import types

import pytest

# Run as main module for unit tests.
def test_namednumber():
    ONE = types.NamedNumber(1, "one")
    OTHERONE = types.NamedNumber(1, "OTHERONE")
    print(ONE)
    assert ONE == OTHERONE
    assert ONE == 1
    assert str(ONE) == "one"

def test_namednumberset():
    numset = types.NamedNumberSet("zero", "one", "two", "three")
    assert len(numset) == 4
    assert numset[0] == 0
    assert numset[1] == 1
    assert str(numset[1]) == "one"

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
