"""
Unit tests for devtest.config module.
"""

from devtest import config


class TestConfig:

    def setup_method(self):
        cf = config.get_config()
        self._cf = cf

    def test_get(self):
        cf = self._cf
        assert bool(cf)

    def test_same(self):
        cf = config.get_config()
        assert id(cf) == id(self._cf)

    def test_read_default(self):
        cf = self._cf
        assert cf["database"]["url"].startswith("postgres")

    def test_flags(self):
        cf = self._cf
        cf.flags.debug


class TestConfigUpdate:

    def test_with_initdict(self):
        config._CONFIG = None
        cf = config.get_config(initdict={"base.tree": "value"})
        assert cf.base.tree == "value"


def test_module():
    config._test([])

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
