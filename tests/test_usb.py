
"""Unit tests for devtest.usb module.
"""

import sys
import os
import subprocess

import pytest

from devtest import usb

UNAME = os.uname()
HOSTNAME = UNAME.nodename

NO_PIXEL = subprocess.run(['lsusb', '-d', '18d1:4ee7']).returncode != 0


def test_libusberror_str():
    assert str(usb.LibusbError(-2)) == "Invalid parameter"


def test_device_count():
    session = usb.UsbSession()
    count = session.device_count
    assert count > 0
    print("device count:", count)
    del session


def test_find_device():
    session = usb.UsbSession()
    if sys.platform == "darwin":  # TODO a better MacOS selector
        dev = session.find(0x05ac, 0x0274) # Apple keyboard and trackpad
    else:
        dev = session.find(0x1d6b, 0x0002) # Linux Foundation 2.0 root hub
    del session
    assert dev is not None
    print(dev)


@pytest.mark.skipif(HOSTNAME != "mercury", reason="Needs author's host.")
def test_parent():
    session = usb.UsbSession()
    dev = session.find(0x0a12, 0x0001) # Cambridge Silicon Radio, Ltd Bluetooth Dongle (HCI mode)
    assert dev is not None
    print(dev)
    dev2 = dev.parent
    print(dev2)
    assert dev2 is not None
    del session


@pytest.mark.skipif(HOSTNAME != "mercury", reason="Needs author's host.")
def test_device_class():
    session = usb.UsbSession()
    dev = session.find(0x0a12, 0x0001) # Cambridge Silicon Radio, Ltd Bluetooth Dongle (HCI mode)
    assert dev is not None
    print(dev)
    print(dev.Class)
    assert isinstance(dev.Class, usb.DeviceClass)


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_open():
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7) # Google Pixel XL
    assert dev is not None
    dev.open()
    conf = dev.configuration
    assert conf is not None, "Got None for configuration on opened device."
    dev.close()


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_operate_on_closed():
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7) # Google Pixel XL
    assert dev is not None
    try:
        conf = dev.configuration
    except usb.UsbUsageError as err:
        pass
    else:
        raise AssertionError("Didn't raise UsbUsageError as expected.")


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_open_str():
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7) # Google Pixel XL
    assert dev is not None
    s = str(dev)
    print(s)
    assert "closed" in s
    dev.open()
    s = str(dev)
    assert "open" in s
    print(s)
    dev.close()


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_find_device_with_serial():
    ANDROID_SERIAL = os.environ.get("ANDROID_SERIAL")
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7, serial=ANDROID_SERIAL) # Google Pixel XL
    assert dev is not None
    dev.open()
    print(dev)
    assert dev.serial == ANDROID_SERIAL
    dev.close()


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_configurations():
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7)
    for cf in dev.configurations:
        assert isinstance(cf, usb.Configuration)
        print(cf)


@pytest.mark.skipif(NO_PIXEL, reason="Needs attached Pixel XL.")
def test_active_configuration():
    session = usb.UsbSession()
    dev = session.find(0x18d1, 0x4ee7)
    cf = dev.active_configuration
    assert isinstance(cf, usb.Configuration)
    print(cf)



# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
