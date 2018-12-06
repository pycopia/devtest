#!/usr/bin/python3.6

"""Controllers for Android based products.  """

from __future__ import generator_stop

from devtest import devices
from devtest.devices.android import adb
from devtest.devices.android import sl4a

import uiautomator


class AndroidController(devices.Controller):
    """Controller for Android phone.

    Collects together various Android device interfaces and provides a unified API.

    Properties:
        adb: An adb.AndroidDeviceClient instance.
        uia: An uiautomator.Device instance.
        api: An sl4a.SL4AInterface instance.
    """

    def __init__(self, equipment):
        self._equipment = equipment
        self._adb = None
        self._uia = None
        self._api = None


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

    @property
    def api(self):
        if self._api is None:
            self._api = sl4a.SL4AInterface(self.adb)
            self._api.connect()
        return self._api

    def close(self):
        if self._api is not None:
            self._api.close()
            self._api = None
        if self._uia is not None:
            self._uia = None
        if self._adb is not None:
            self._adb.close()
            self._adb = None

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
