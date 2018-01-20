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
