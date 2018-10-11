#!/usr/bin/python3.6

"""Controllers for Android based products.  """

from __future__ import generator_stop

from devtest import devices
from devtest.devices.android import adb

import uiautomator


class AndroidController(devices.Controller):
    """Controller for Android phone."""

    def __init__(self, equipment):
        self._equipment = equipment
        self._adb = None
        self._uia = None


    @property
    def adb(self):
        if self._adb is None:
            self._adb = adb.AndroidDeviceClient(self._equipment["serno"])
        return self._adb

    @property
    def uia(self):
        if self._uia is None:
            self._uia = uiautomator.Device(self._equipment["serno"])
        return self._uia

    def close(self):
        if self._adb is not None:
            self._adb.close()
            self._adb = None
        if self._uia is not None:
            self._uia = None


if __name__ == "__main__":
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
