"""
Unit test devtest.os modules.
"""

from __future__ import generator_stop


from .util import run_module


def test_os_process():
    run_module("devtest.os.process")


def test_os_time():
    run_module("devtest.os.time")


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
