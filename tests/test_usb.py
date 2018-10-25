
"""Unit tests for devtest.usb module.
"""

import sys

import pytest

from devtest import usb


def test_device_count():
    bus = usb.Usb()
    count = bus.device_count
    assert count > 0
    print("device count:", count)
    del bus

def test_find_device():
    bus = usb.Usb()
    if sys.platform == "darwin":  # TODO a better MacOS selector
        dev = bus.find(0x05ac, 0x0274) # Apple keyboard and trackpad
    else:
        dev = bus.find(0x1d6b, 0x0002) # Linux Foundation 2.0 root hub
    del bus
    assert dev is not None
    print(dev)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
