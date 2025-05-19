"""Controllers for Android based products."""

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from array import array
from ast import literal_eval
from datetime import datetime, timezone
import io
import os
import re
import stat

from devtest import logging
from devtest import devices
from devtest.core import exceptions
from devtest.devices.android import adb
from devtest.devices.android import sl4a
from devtest.devices.android import snippets
from devtest.devices.android import uiautomator
from devtest.io import reactor
from devtest.os import cpuinfo
from devtest.os import meminfo


class AndroidControllerError(exceptions.ControllerError):
    """Raised for errors from the AndroidController."""


class AndroidController(devices.Controller):
    """Controller for Android phone.

  Collects together various Android device interfaces and provides a unified
  API.

  Properties:
      adb: An adb.AndroidDeviceClient instance.
      uia: An uiautomator.AutomatorDevice instance.
      api: An sl4a.SL4AInterface instance.
      snippets: An snippets.SnippetsInterface instance.
      properties: A dictionary of all Android property values (from getprop).
      currenttime: Device's current time.
      settings: Access to settings.
      buttons: Access to button press interaction.
      thermal: Access to thermal information
      meminfo: Memory information and monitor for a process.
      processinfo: CPU information and monitors for a process.
  """

    _PROPERTY_RE = re.compile(r'\[(.*)\]: \[(.*)\]')

    def __init__(self, equipment):
        super().__init__(equipment)
        self._adb = None
        self._uia = None
        self._api = None
        self._snippets = None

    def close(self):
        """Free controller resources."""
        if self._api is not None:
            self._api.close()
            self._api = None
        if self._uia is not None:
            self._uia.close()
            self._uia = None
        if self._adb is not None:
            self._adb.close()
            self._adb = None
        if self._snippets is not None:
            self._snippets.close()
            self._snippets = None

    @property
    def adb(self):
        """The ADB protocol client instance."""
        if self._adb is None:
            self._adb = adb.AndroidDeviceClient(self._equipment['serno'])
        else:
            self._adb.open()
        return self._adb

    @adb.deleter
    def adb(self):
        if self._adb is not None:
            self._adb.close()

    @property
    def uia(self):
        """A UI automator instance."""
        if self._uia is None:
            self._uia = uiautomator.AutomatorDevice(self._equipment['serno'])
            self._uia.wakeup()
        return self._uia

    @uia.deleter
    def uia(self):
        self._uia.close()
        self._uia = None

    @property
    def api(self):
        """The SL4A interface."""
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
        """The Android snippets interface."""
        if self._snippets is None:
            aadb = adb.getAsyncAndroidDeviceClient(self._equipment['serno'])
            self._snippets = snippets.SnippetsInterface(aadb, self._equipment['serno'])
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
        regex = AndroidController._PROPERTY_RE
        text = self.shell(['getprop'])
        for line in text.splitlines():
            m = regex.search(line)
            if m:
                name, value = m.group(1, 2)
                pd[name] = value
        return pd

    @property
    def currenttime(self):
        """Return device's time as datetime object, UTC timezone."""
        out = self.shell('date -u +%s.%N')
        return datetime.fromtimestamp(float(out), tz=timezone.utc)

    def shell(self, cmd, usepty=False):
        """Run a shell command and return stdout.

    Args:
        cmd: list or string, command to run

    Returns:
        The stdout as str (decoded).

    Raises:
        AndroidControllerError with exit status and stderr as args.
    """
        logging.info(f'AndroidController.shell({cmd!r}, usepty={usepty!r})')
        stdout, stderr, es = self.adb.command(cmd, usepty=usepty)
        if es:
            return stdout
        raise AndroidControllerError((es, stderr))

    def activity(
        self,
        package=None,
        component=None,
        command='start',
        action='android.intent.action.MAIN',
        user=None,
        data=None,
        mimetype=None,
        wait=True,
        force_stop=False,
        identifier=None,
        **extra,
    ):
        """Start an activity on device.

    This also force-stops a prior instance.

    Args:
        package: str with package name.
        activity: str with activity name.
        action: str of action, default is 'android.intent.action.MAIN'.

    Extra options may be supplied as additional keyword arguments.

    Returns:
        output of activity start command.
    """
        cmd = ['cmd', 'activity', command]
        if wait:
            cmd.append('-W')
        if force_stop:
            cmd.append('-S')
        if user:
            cmd.append('--user')
            cmd.append(str(user))
        # INTENT
        if action:
            if action == 'android.intent.action.MAIN':
                cmd.append('-S')
            cmd.append('-a')
            cmd.append(str(action))
        if data is not None:
            cmd.append('-d')
            cmd.append(str(data))
        if mimetype is not None:
            cmd.append('-t')
            cmd.append(str(mimetype))
        if identifier is not None:
            cmd.append('-i')
            cmd.append(str(identifier))
        if package and component:
            cmd.append('-n')
            cmd.append(f'{package}/{component}')
        elif package:
            cmd.append(package)
        # extras
        for key, value in extra.items():
            if value is not None:
                option, optionval = _intent_extra_type(value)
                cmd.extend([option, key, optionval])
        out = self.shell(cmd)
        if 'Error:' in out:
            raise AndroidControllerError(out)
        return out

    def stop_activity(self, package):
        """Stop a package from running.

    Arguments:
        package: name (str) of package to stop.
    """
        cmd = ['cmd', 'activity', 'force-stop', package]
        return self.shell(cmd)

    def package(self, cmd, *args, user=None, **kwargs):
        """Manage packages using ADB."""
        return self.adb.package(cmd, *args, user=user, **kwargs)

    def bugreport(self, localfile):
        """Pull a bug report directly to a local file."""
        return self.adb.bugreport(localfile)

    def instrument(self, package, runner, wait=False, **extra):
        """Run instrumented code like 'am instrument'."""
        cmd = ('export CLASSPATH=/system/framework/am.jar; '
               'exec app_process /system/bin com.android.commands.am.Am instrument')
        if wait:
            cmd += ' -w'
        for name, value in extra.items():
            cmd += f' -e "{name}" "{value}"'
        cmd += f' "{package}/{runner}"'
        return self.shell(cmd)

    def pgrep(self, pattern):
        """Run pgrep and returns a list of PIDs and names matching pattern."""
        rv = []
        out, _, es = self.adb.command(['pgrep', '-l', '-f', pattern])
        if es and out:
            for line in out.splitlines():
                pid, cmd = line.split(None, 1)
                rv.append((int(pid), cmd))
        return rv

    def meminfo(self, pid):
        """Fetch and monitor memory usage for a process.

    Returns MemoryMonitor instance with PID.

    Args:
        pid: (int) PID of process to get memory information for.

    Returns:
        MemoryMonitor instance for attached device and PID.
    """
        return MemoryMonitor(self.adb, pid)

    def processinfo(self, name: str = None, pid: int = None) -> 'ProcessInfo':
        """Access information about a process on device.

    Args:
        pid: (int) PID of process to get CPU information for.

    Returns:
        ProcessInfo instance for attached device and PID.
    """
        if pid is not None:
            return ProcessInfo(self.adb, int(pid))
        if name is not None:
            plist = self.pgrep(name)
            if len(plist) == 1:
                return ProcessInfo(self.adb, plist[0][0])
            raise ValueError('Ambiguous process name, or not found. Select only one.')
        raise ValueError('processinfo: must supply either PID or name of process.')

    def listdir(self, path):
        """Return a list of names in a directory."""
        result = []

        def cb(_, name):
            nonlocal result
            result.append(name)

        self.adb.list(path, cb)
        return result

    def push(self, localfiles: list | str, remotepath: str, sync: bool = False):
        """Push a local file for list of file paths to remove device."""
        if not isinstance(localfiles, list):
            localfiles = [localfiles]
        return self.adb.push(localfiles, remotepath, sync=sync)

    def pull(self, remotepath, localpath):
        """Copy a device file to a local file."""
        return self.adb.pull(remotepath, localpath)

    def exists(self, remotepath):
        """Test if a remote file exists on device."""
        try:
            self.adb.stat(remotepath)
        except FileNotFoundError:
            return False
        return True

    def stat(self, remotepath):
        """Get file system information on path."""
        return self.adb.stat(remotepath)

    def unlink(self, remotepath):
        """unlink/delete a file on device."""
        self.shell(f'unlink {remotepath}')

    def get_property(self, name):
        """Get a single Android property."""
        return self.shell(['getprop', name]).strip()

    def set_property(self, name, value):
        """Set a single Android property."""
        return self.shell(['setprop', name, value]).strip()

    def get_state(self):
        """Return device state using a method that does not require it to be

    authorized.
    """
        client = adb.AdbClient()
        return client.get_state(self._equipment['serno'])

    def reconnect(self):
        """Cause device to reconnect to adb.

    Wait for it to become known to adb again.
    """
        del self.adb
        c = adb.AdbClient()
        c.reconnect(self._equipment['serno'])
        c.close()

    def airplane_mode(self, onoff):
        """Set airplane mode on or off."""
        original_mode = int(self.shell(['settings', 'get', 'global', 'airplane_mode_on']))
        if original_mode == onoff:
            return original_mode
        self.shell(['settings', 'put', 'global', 'airplane_mode_on', str(int(onoff))])
        self.shell([
            'am',
            'broadcast',
            '-a',
            'android.intent.action.AIRPLANE_MODE',
            '--ez',
            'state',
            'true' if onoff else 'false',
        ])
        val = self.shell(['settings', 'get', 'global', 'airplane_mode_on'])
        if int(val.strip()) != onoff:
            raise AndroidControllerError("Didn't set airplane mode.")
        return original_mode

    def svc_wifi(self, onoff):
        """WiFi enable/disable."""
        return self.shell(['svc', 'wifi', 'enable' if onoff else 'disable'])

    def svc_data(self, onoff):
        """Data enable/disable."""
        return self.shell(['svc', 'data', 'enable' if onoff else 'disable'])

    def svc_nfc(self, onoff):
        """NFC enable/disable."""
        return self.shell(['svc', 'nfc', 'enable' if onoff else 'disable'])

    def svc_bluetooth(self, onoff):
        """Bluetooth enable/disable."""
        return self.shell(['svc', 'bluetooth', 'enable' if onoff else 'disable'])

    def stay_awake(self, onoff):
        """Screen will never sleep while charging."""
        # TODO(dart) handle: svc power stayon [true|false|usb|ac|wireless]
        if onoff:
            return self.shell(['svc', 'power', 'stayon', 'usb'])
        return self.shell(['svc', 'power', 'stayon', 'false'])

    def reboot(self):
        """Reboot the device."""
        # This needs to be handled specially
        cmd = ['svc', 'power', 'reboot', 'Reboot by controller command']
        adbclient = self.adb
        self._adb = None
        self.close()
        stdout, stderr, es = adbclient.command(cmd)
        adbclient.close()
        if es:
            return stdout
        raise AndroidControllerError((es, stderr))

    def shutdown(self):
        """Perform runtime shutdown and power off.

    You won't have access to this device at all after this.
    """
        cmd = ['svc', 'power', 'shutdown']
        adbclient = self.adb
        self._adb = None
        self.close()
        stdout, stderr, es = adbclient.command(cmd)
        adbclient.close()
        if es:
            return stdout
        raise AndroidControllerError((es, stderr))

    @property
    def settings(self):
        """Android settings."""
        return _Settings(self)

    @property
    def buttons(self):
        """Use some buttons using kernel event injection."""
        return _Buttons(self)

    # thermal management
    @property
    def thermal(self):
        """Access to thermal management."""
        return _Thermal(self)

    @property
    def logcat(self):
        """Access to special logcat functions."""
        return adb.LogcatHandler(self.adb.async_client)


class _Buttons:

    def __init__(self, controller):
        self._cont = controller

    def press(self, keycode):
        """Insert a a keyevent for the given keycode.

    See: https://developer.android.com/reference/android/view/KeyEvent
    for possible codes.
    """
        return self._cont.shell(['input', 'keyevent', keycode])

    def power(self):
        """Wake up device by using wakeup key."""
        return self.press('KEYCODE_WAKEUP')

    def back(self):
        """Press Back button."""
        return self.press('KEYCODE_BACK')

    def home(self):
        """Press Home button."""
        return self.press('KEYCODE_HOME')

    def volume_up(self):
        """Press volume up."""
        return self.press('KEYCODE_VOLUME_UP')

    def volume_down(self):
        """Press volume down."""
        return self.press('KEYCODE_VOLUME_DOWN')


class _Thermal:
    """Access Android thermal subsystem."""

    THERMAL_ENGINE_CONFIG = '/vendor/etc/thermal-engine.conf'
    THERMAL_BASE = '/sys/devices/virtual/thermal'

    def __init__(self, controller):
        self._cont = controller
        self._config = self._parse_config(self.THERMAL_ENGINE_CONFIG)
        self._board_temp_file = self._find_board_temp_file()

    def _parse_config(self, cfpath):
        """Parse the thermal-engine config file to a dictionary."""
        d = {}
        text = self._cont.shell(['cat', cfpath])
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('['):
                section_name = line[1:-1]
                d[section_name] = section = {}
            else:
                option, value = line.split(None, 1)
                section[option] = (value.split() if '\t' in value else _evaluate_value(value))
        return d

    def _find_board_temp_file(self):
        """Find the thermal subystem temperature file.

    To use for the board temperature.

    Use the THROTTLING-NOTIFY2 config.
    """
        config_section = self._config.get('THROTTLING-NOTIFY2')
        if config_section is None:
            raise AndroidControllerError('No THROTTLING-NOTIFY2 section in config')
        # Find the right thermal_zone path for that sensor type.
        sensor_type = config_section['sensor']
        sensor_path = None
        ac = self._cont.adb.async_client

        async def match_entry(st, name):
            nonlocal sensor_path
            if stat.S_ISDIR(st.st_mode):
                if name.startswith('thermal_zone'):
                    tpath = os.path.join(self.THERMAL_BASE, name, 'type')
                    out, _, es = await ac.command(['cat', tpath])
                    if es:
                        if out.strip() == sensor_type:
                            sensor_path = os.path.join(self.THERMAL_BASE, name, 'temp')

        reactor.get_kernel().run(ac.list(self.THERMAL_BASE, match_entry))
        return sensor_path

    @property
    def board_temperature(self):
        """The current board temperature, in Deg C."""
        out, _, es = self._cont.adb.command(['cat', self._board_temp_file])
        if es:
            return int(out.strip())
        raise AndroidControllerError(
            f"Couldn't read board temperature file: {self._board_temp_file}")


def _intent_extra_type(value):
    """Figure out the intent extra type option from the Python type.

  Best effort, might not work for all cases.
  """
    if isinstance(value, str):
        return '--es', value
    if isinstance(value, bool):
        return '--ez', 'true' if value else 'false'
    if isinstance(value, int):
        if value.bit_length() <= 32:
            return '--ei', str(value)
        return '--el', str(value)
    if isinstance(value, float):
        return '--ef', str(value)
    if isinstance(value, list):
        if all(isinstance(v, int) for v in value):
            return '--eial', ','.join(str(v) for v in value)
        if all(isinstance(v, float) for v in value):
            return '--efa', ','.join(str(v) for v in value)
        if all(isinstance(v, str) for v in value):
            return '--esa', ','.join(value)
    elif isinstance(value, array):
        if value.typecode == 'i':
            return '--eia', ','.join(value)
    raise ValueError(f"Don't have conversion for type: {type(value)}")


def _evaluate_value(value):
    if value == 'null':
        return None
    try:
        return literal_eval(value)
    except:  # noqa
        return value


class _Settings:
    """Manage Android settings.

  Wrapper for the "settings" command on Android.
  Maps to and from Python objects as much as possible.

    get  NAMESPACE KEY
        Retrieve the current value of KEY.
    put  NAMESPACE KEY VALUE [TAG] [default]
        Change the contents of KEY to VALUE.
        TAG to associate with the setting.
        {default} to set as the default, case-insensitive only for global/secure
        namespace
    delete NAMESPACE KEY
        Delete the entry for KEY.
    reset  NAMESPACE {PACKAGE_NAME | RESET_MODE}
        Reset the global/secure table for a package with mode.
        RESET_MODE is one of
          {untrusted_defaults, untrusted_clear, trusted_defaults},
          case-insensitive
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
            return 'null'
        if value in (True, False):
            return str(int(value))
        return str(value)

    def get(self, namespace, key):
        """Get a setting."""
        val = self._cont.shell(['settings', 'get', namespace, key])
        return _evaluate_value(val)

    def put(self, namespace, key, value, tag=None, default=None):
        """Put a setting."""
        value = self._encode(value)
        cmd = ['settings', 'put', namespace, key, value]
        if tag is not None:
            cmd.append(str(tag))
        if default is not None:
            cmd.append(str(default))
        return self._cont.shell(cmd)

    def delete(self, namespace, key):
        """Delete a setting."""
        return self._cont.shell(['settings', 'delete', namespace, key])

    def list(self, namespace):
        """Return a dict of all settings in a namespace."""
        rv = {}
        out = self._cont.shell(['settings', 'list', namespace])
        for line in out.splitlines():
            key, val = line.split('=', 1)
            rv[key] = _evaluate_value(val)
        return rv

    def reset(self, namespace, mode):
        """Reset settings."""
        if mode not in {
                'untrusted_defaults',
                'untrusted_clear',
                'trusted_defaults',
        }:
            raise ValueError('mode must be one of:'
                             '"untrusted_defaults", "untrusted_clear", '
                             '"trusted_defaults"')
        if namespace not in {'global', 'secure'}:
            raise ValueError('namespace must be one of: "global", "secure"')
        return self._cont.shell(['settings', 'reset', namespace, mode])

    # Methods for settings that require special handling follow
    def location(self, onoff):
        """Set location service on or off."""
        # The location_providers_allowed setting is a list, you add and
        # remove providers using "+" and "-" prefix, respectively. When all
        # are removed, the location service is disabled.
        if onoff:
            # TODO(dart) fix hard-coded defaults
            self._cont.shell(['settings', 'put', 'secure', 'location_providers_allowed', '+gps'])
            self._cont.shell([
                'settings',
                'put',
                'secure',
                'location_providers_allowed',
                '+network',
            ])
        else:
            locations = self._cont.shell(
                ['settings', 'get', 'secure', 'location_providers_allowed'])
            locations = locations.strip()
            if locations:
                for provider in locations.split(','):
                    self._cont.shell([
                        'settings',
                        'put',
                        'secure',
                        'location_providers_allowed',
                        '-' + provider,
                    ])


class MemoryMonitor:
    """Monitor a process memory usage."""

    CLEAR_REFS = '/proc/{pid}/clear_refs'

    def __init__(self, adbclient, pid):
        self._adb = adbclient
        self._pid = pid
        self._startmap = None
        self._stopmap = None

    def start(self):
        """Start the monitor."""
        self._stopmap = None
        self._startmap = self.current()
        path = MemoryMonitor.CLEAR_REFS.format(pid=self._pid)
        _, _, es = self._adb.command(['echo', '1', '>', path])
        if not es:
            raise AndroidControllerError(es)

    def current(self):
        """Get current memory map."""
        path = meminfo.Maps.SMAPS.format(pid=self._pid)
        with io.BytesIO() as bio:
            self._adb.pull_file(path, bio)
            return meminfo.Maps.from_text(bio.getvalue())

    def stop(self):
        """Stop the monitor."""
        if self._startmap is None:
            raise RuntimeError('Stopping memory monitor before starting.')
        self._stopmap = self.current()

    def difference(self):
        """Different between start and end values."""
        if self._startmap is None or self._stopmap is None:
            raise RuntimeError('MemoryMonitor was not run.')
        new = meminfo.get_memusage_defaults()
        memstop = self._stopmap.rollup()._asdict()
        memstart = self._startmap.rollup()._asdict()
        for fname in meminfo.MemUsage._fields:
            if fname == 'VmFlags':
                continue
            new[fname] = memstop[fname] - memstart[fname]
        return meminfo.MemUsage(**new)

    def referenced_pages(self):
        """return number of pages referenced during the time span."""
        if self._stopmap is None:
            raise RuntimeError('MemoryMonitor was not run.')
        memstop = self._stopmap.rollup()
        return memstop.Referenced // memstop.KernelPageSize


class CPUMonitor:
    """Monitor a process CPU utilization."""

    def __init__(self, adbclient, pid):
        self._adb = adbclient
        self._pid = pid
        self._path = f'/proc/{pid:d}/stat'
        self._start_jiffies = None
        self._starttime = None

    def get_timestamp(self):
        """Get wall clock since boot."""
        with io.BytesIO() as bio:
            self._adb.pull_file('/proc/uptime', bio)
            text = bio.getvalue()
        # Wall clock since boot, combined idle time of all cpus
        clock, _ = text.split()
        return float(clock)

    def get_procstat(self):
        """Get the ProcStat for process."""
        with io.BytesIO() as bio:
            self._adb.pull_file(self._path, bio)
            ps = cpuinfo.ProcStat.from_text(bio.getvalue())
        return ps

    def start(self):
        """Start monitor by recording current state."""
        self._starttime = self.get_timestamp()
        ps = self.get_procstat()
        self._start_jiffies = ps.stime + ps.utime

    def current(self):
        """Return CPU utilization, as percent (float).

    The start method must be called first.
    """
        now = self.get_timestamp()
        ps = self.get_procstat()
        current_jiffies = ps.stime + ps.utime
        return float(current_jiffies - self._start_jiffies) / (now - self._starttime)

    def end(self):
        """Stop monitor.

    Returns:
        Elapsed time of run, in seconds (float).
    """
        st = self._starttime
        self._starttime = None
        self._start_jiffies = None
        return self.get_timestamp() - st


class ProcessInfo:
    """Access point to information about a process on device."""

    def __init__(self, adbclient, pid):
        self._adb = adbclient
        self._pid = pid
        self._mm = None
        self._cpum = None

    @property
    def memory_monitor(self):
        """A memory monitor."""
        if self._mm is None:
            self._mm = MemoryMonitor(self._adb, self._pid)
        return self._mm

    @memory_monitor.deleter
    def memory_monitor(self):
        self._mm = None

    @property
    def cpu_monitor(self):
        """A CPU monitor."""
        if self._cpum is None:
            self._cpum = CPUMonitor(self._adb, self._pid)
        return self._cpum

    @cpu_monitor.deleter
    def cpu_monitor(self):
        self._cpum = None
