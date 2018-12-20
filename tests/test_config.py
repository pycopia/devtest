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
Unit tests for devtest.settings module.
"""

import unittest

from devtest import config


class ConfigTests(unittest.TestCase):


    def setUp(self):
        cf = config.get_config()
        self._cf = cf

    def test_1get(self):
        cf = self._cf
        self.assertTrue(bool(cf))

    def test_2same(self):
        cf = config.get_config()
        self.assertEqual(id(cf), id(self._cf))

    def test_3read_default(self):
        cf = self._cf
        self.assertTrue(cf["database"]["url"].startswith("postgres"))

    def test_1flags(self):
        cf = self._cf
        cf.flags.debug


class ConfigUpdateTests(unittest.TestCase):

    def test_with_initdict(self):
        config._CONFIG = None
        cf = config.get_config(initdict={"base.tree": "value"})
        assert cf.base.tree == "value"


def test_module():
    config._test([])

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
