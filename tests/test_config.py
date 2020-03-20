"""
Unit tests for devtest.config module.
"""

import pytest

from devtest import config


@pytest.fixture
def cf():
    return config.get_config()


class TestConfig:

    def test_is_singleton(self, cf):
        newcf = config.get_config()
        assert id(newcf) == id(cf)

    def test_read_default(self, cf):
        assert cf["flags"]["debug"] == 0
        assert cf["flags"]["verbose"] == 0

    def test_attribute_access(self, cf):
        cf.flags.debug = 1
        assert cf.flags.debug == 1


class TestConfigUpdate:

    def test_with_initdict(self):
        config._CONFIG = None
        cf = config.get_config(initdict={"base.tree": "value"})
        assert cf.base.tree == "value"

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
