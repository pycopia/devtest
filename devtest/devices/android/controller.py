# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Controllers for Android based products.  """

from __future__ import generator_stop

import re
from ast import literal_eval

from devtest import devices
from devtest.core import exceptions
from devtest.devices.android import adb
from devtest.devices.android import sl4a
from devtest.devices.android import snippets

import uiautomator


class AndroidControllerError(exceptions.ControllerError):
    """Raised for errors from the AndroidController."""


class AndroidController(devices.Controller):
    """Controller for Android phone.

    Collects together various Android device interfaces and provides a unified API.

    Properties:
        adb: An adb.AndroidDeviceClient instance.
        uia: An uiautomator.Device instance.
        api: An sl4a.SL4AInterface instance.
        snippets: An snippets.SnippetsInterface instance.
        properties: A dictionary of all Android property values (from getprop).
    """

    _PROPERTY_RE = re.compile(r"\[(.*)\]: \[(.*)\]")

    def __init__(self, equipment):
        self._equipment = equipment
        self._adb = None
        self._uia = None
        self._api = None
        self._snippets = None

    def close(self):
        if self._api is not None:
            self._api.close()
            self._api = None
        if self._uia is not None:
            self._uia = None
        if self._adb is not None:
            self._adb.close()
            self._adb = None
        if self._snippets is not None:
            self._snippets.close()
            self._snippets = None

    @property
    def adb(self):
        if self._adb is None:
            self._adb = adb.AndroidDeviceClient(self._equipment["serno"])
        else:
            self._adb.open()
        return self._adb

    @adb.deleter
    def adb(self):
        if self._adb is not None:
            self._adb.close()

    @property
    def uia(self):
        if self._uia is None:
            # TODO(dart) uiautomator.Device has reliability issues. Need a
            # wrapper.
            self._uia = uiautomator.Device(self._equipment["serno"])
        return self._uia

    @uia.deleter
    def uia(self):
        self._uia = None

    @property
    def api(self):
        if self._api is None:
            self._api = sl4a.SL4AInterface(self.adb)
            self._api.connect()
        return self._api

    @api.deleter
    def api(self):
        if self._api is not None:
            self._api.close()
            self._api = None

    @property
    def snippets(self):
        if self._snippets is None:
            aadb = adb.getAsyncAndroidDeviceClient(self._equipment["serno"])
            self._snippets = snippets.SnippetsInterface(aadb, self._equipment["serno"])
        return self._snippets

    @snippets.deleter
    def snippets(self):
        if self._snippets is not None:
            self._snippets.close()
            self._snippets = None

    @property
    def properties(self):
        """The Android properties."""
        pd = {}
        RE = AndroidController._PROPERTY_RE
        text = self.shell(["getprop"])
        for line in text.splitlines():
            m = RE.search(line)
            if m:
                name, value = m.group(1, 2)
                pd[name] = value
        return pd

    @property
    def settings(self):
        """Android settings."""
        return _Settings(self)

    def shell(self, cmd):
        """Run a shell command and return stdout.

        Args:
            cmd: list or string, command to run

        Returns:
            The stdout as str (decoded).

        Raises:
            AndroidControllerError with exit status and stderr as args.
        """
        stdout, stderr, es = self.adb.command(cmd)
        if es:
            return stdout
        else:
            raise AndroidControllerError((es, stderr))

    def get_property(self, name):
        """Get a single Android property.
        """
        return self.shell(["getprop", name]).strip()

    def set_property(self, name, value):
        """Set a single Android property.
        """
        return self.shell(["setprop", name, value]).strip()

    def get_state(self):
        """Return device state using a method that does not require it to be
        authorized.
        """
        client = adb.AdbClient()
        return client.get_state(self._equipment["serno"])

    def reconnect(self):
        """Cause device to reconnect to adb.

        Wait for it to become known to adb again.
        """
        return adb.AdbClient().reconnect(self._equipment["serno"])

    def airplane_mode(self, onoff):
        """Set airplane mode on or off.
        """
        original_mode = int(self.shell(['settings', 'get', 'global',
                                       'airplane_mode_on']))
        if original_mode == onoff:
            return original_mode
        self.shell(['settings', 'put', 'global', 'airplane_mode_on',
                    str(int(onoff))])
        self.shell(['am', 'broadcast',
                    '-a', 'android.intent.action.AIRPLANE_MODE',
                    '--ez', 'state', 'true' if onoff else 'false'])
        val = self.shell(['settings', 'get', 'global', 'airplane_mode_on'])
        if int(val.strip()) != onoff:
            raise AndroidControllerError("Didn't set airplane mode.")
        return original_mode

    def svc_wifi(self, onoff):
        return self.shell(['svc', 'wifi', 'enable' if onoff else 'disable'])

    def svc_data(self, onoff):
        return self.shell(['svc', 'data', 'enable' if onoff else 'disable'])

    def svc_nfc(self, onoff):
        return self.shell(['svc', 'nfc', 'enable' if onoff else 'disable'])

    def svc_bluetooth(self, onoff):
        return self.shell(['svc', 'bluetooth', 'enable' if onoff else 'disable'])
    # TODO(dart) usb          Control Usb state

    def reboot(self):
        """Reboot the device."""
        # This needs to be handled specially
        cmd = ['svc', 'power', 'reboot', 'Reboot by controller command']
        adb = self.adb
        self._adb = None
        self.close()
        stdout, stderr, es = adb.command(cmd)
        adb.close()
        if es:
            return stdout
        else:
            raise AndroidControllerError((es, stderr))

    def shutdown(self):
        """Perform runtime shutdown and power off.

        You won't have access to this device at all after this.
        """
        cmd = ['svc', 'power', 'shutdown']
        adb = self.adb
        self._adb = None
        self.close()
        stdout, stderr, es = adb.command(cmd)
        adb.close()
        if es:
            return stdout
        else:
            raise AndroidControllerError((es, stderr))


class _Settings:
    """Manage Android settings.

    Wrapper for the "settings" command on Android.
    Maps to and from Python objects as much as possible.

      get  NAMESPACE KEY
          Retrieve the current value of KEY.
      put  NAMESPACE KEY VALUE [TAG] [default]
          Change the contents of KEY to VALUE.
          TAG to associate with the setting.
          {default} to set as the default, case-insensitive only for global/secure namespace
      delete NAMESPACE KEY
          Delete the entry for KEY.
      reset  NAMESPACE {PACKAGE_NAME | RESET_MODE}
          Reset the global/secure table for a package with mode.
          RESET_MODE is one of
            {untrusted_defaults, untrusted_clear, trusted_defaults}, case-insensitive
      list NAMESPACE
          Print all defined keys.
          NAMESPACE is one of {system, secure, global}, case-insensitive

    Example:
        all_global = device.settings.list("global")
    """

    def __init__(self, controller):
        self._cont = controller

    def _encode(self, value):
        if value is None:
            return "null"
        elif value in (True, False):
            return str(int(value))
        else:
            return str(value)

    def _decode(self, value):
        if value == "null":
            return None
        try:
            return literal_eval(value)
        except:  # noqa
            return value

    def get(self, namespace, key):
        val =  self._cont.shell(['settings', 'get', namespace, key])
        return self._decode(val)

    def put(self, namespace, key, value, tag=None, default=None):
        value = self._encode(value)
        cmd = ['settings', 'put', namespace, key, value]
        if tag is not None:
            cmd.append(str(tag))
        if default is not None:
            cmd.append(str(default))
        return self._cont.shell(cmd)

    def delete(self, namespace, key):
        return self._cont.shell(['settings', 'delete', namespace, key])

    def list(self, namespace):
        """Return a dict of all settings in a namespace.
        """
        rv = {}
        out = self._cont.shell(['settings', 'list', namespace])
        for line in out.splitlines():
            key, val = line.split("=", 1)
            rv[key] = self._decode(val)
        return rv

    def reset(self, namespace, mode):
        if mode not in {"untrusted_defaults", "untrusted_clear", "trusted_defaults"}:
            raise ValueError('mode must be one of:'
                             '"untrusted_defaults", "untrusted_clear", '
                             '"trusted_defaults"')
        if namespace not in {"global", "secure"}:
            raise ValueError('namespace must be one of: "global", "secure"')
        return self._cont.shell(['settings', 'reset', namespace, mode])

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
