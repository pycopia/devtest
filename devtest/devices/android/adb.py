# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Native adb client-to-server protocol implementation.

This is an async implementation, suitable for including in an event loop.
"""

import os
import sys
import enum
import stat
import errno
import struct
import signal

from devtest import logging
from devtest import timers
from devtest import ringbuffer
from devtest.io import socket
from devtest.io import streams
from devtest.os import process
from devtest.os import procutils
from devtest.os import exitstatus
from devtest.io.reactor import (get_kernel, spawn, block_in_thread, sleep,
                                SignalEvent, timeout_after, TaskTimeout)


ADB = procutils.which("adb")
if ADB is None:
    raise ImportError("The adb program was not found in PATH. "
                      "This module will not work.")

ADB_PORT = 5037

MAX_PAYLOAD_V2 = 256 * 1024
MAX_PAYLOAD = MAX_PAYLOAD_V2


class Error(Exception):
    pass


class AdbProtocolError(Error):
    """An error in the protocol was detected."""


class AdbCommandFail(Error):
    """An error indicated by the server."""


class LogPriority(enum.IntEnum):
    """Logging priority levels."""
    UNKNOWN = 0
    DEFAULT = 1
    VERBOSE = 2
    DEBUG = 3
    INFO = 4
    WARN = 5
    ERROR = 6
    FATAL = 7


class LogId(enum.IntEnum):
    """Source of the log entry.

    See: android/core/include/android/log.h
    """
    MAIN = 0
    RADIO = 1
    EVENTS = 2
    SYSTEM = 3
    CRASH = 4
    STATS = 5
    SECURITY = 6
    KERNEL = 7


def _run_adb(adbcommand):
    """Run the adb binary."""
    cmd = [ADB]
    cmd.extend(adbcommand.split())
    return process.check_output(cmd)


def start_server(port=ADB_PORT):
    return _run_adb("-P {} start-server".format(port))


def kill_server(port=ADB_PORT):
    return _run_adb("-P {} kill-server".format(port))


class AdbConnection:
    """Asynchronous adb socket wrapper."""

    def __init__(self, host="localhost", port=ADB_PORT):
        self.host = host
        self.port = port
        self.socket = None

    async def close(self):
        if self.socket is not None:
            s = self.socket
            self.socket = None
            await s.close()

    def isopen(self):
        return bool(self.socket)

    async def open(self):
        sock = socket.socket(family=socket.AF_INET,
                             type=socket.SOCK_STREAM)
        errno = await sock.connect_ex((self.host, self.port))
        if errno != 0:
            raise IOError(errno, "Could not connect to adb server")
        self.socket = sock

    async def message(self, msg, expect_response=True):
        msg = b"%04x%b" % (len(msg), msg)
        await self.socket.sendall(msg)
        stat = await self.socket.recv(4)
        if stat == b"OKAY":
            if expect_response:
                lenst = await self.socket.recv(4)
                length = int(lenst, 16)
                if length:
                    return await self.socket.recv(length)
                else:
                    return b""
        elif stat == b"FAIL":
            lenst = await self.socket.recv(4)
            length = int(lenst, 16)
            resp = await self.socket.recv(length)
            raise AdbCommandFail("message FAIL: {}".format(resp.decode("ascii")))
        else:
            raise AdbProtocolError(stat.decode("ascii"))

    async def read_protocol_string(self):
        lenst = await self.socket.recv(4)
        length = int(lenst, 16)
        if length:
            return await self.socket.recv(length)
        else:
            return b""


async def _transact(conn, msg):
    await conn.open()
    resp = await conn.message(msg)
    await conn.close()
    return resp


# On the host: 1st OKAY is connect, 2nd OKAY is status.
async def _command_transact(conn, msg):
    await conn.open()
    msg = b"%04x%b" % (len(msg), msg)
    await conn.socket.sendall(msg)
    connstat = await conn.socket.recv(4)
    if connstat == b"OKAY":
        stat = await conn.socket.recv(4)
        if stat != b"OKAY":
            raise AdbCommandFail("command not OKAY")
    elif connstat == b"FAIL":
        lenst = await conn.socket.recv(4)
        length = int(lenst, 16)
        resp = await conn.socket.recv(length)
        await conn.close()
        raise AdbCommandFail(resp.decode("ascii"))
    else:
        await conn.close()
        raise AdbProtocolError(stat.decode("ascii"))


class AdbClient:
    """An adb client, synchronous.

    For general host side operations.
    """
    def __init__(self, host="localhost", port=ADB_PORT):
        self._conn = AdbConnection(host=host, port=port)

    def _message(self, msg):
        if self._conn is None:
            raise Error("Operation on a closed client.")
        return get_kernel().run(_transact(self._conn, msg))

    def close(self):
        if self._conn is not None:
            get_kernel().run(self._conn.close())
            self._conn = None

    def get_device(self, serial):
        """Get a AndroidDeviceClient instance.
        """
        return AndroidDeviceClient(
            serial, host=self._conn.host, port=self._conn.port)

    def get_state(self, serial):
        """Get the current state of a device.

        Arguments:
            serial: str of the device serial number.

        Returns:
            one of {"device", "unauthorized", "bootloader"}
            or None if serial not found.
        """
        for dev in self.get_device_list():
            if dev.serial == serial:
                return dev.state

    def get_device_list(self):
        """Get list of attached devices.

        Returns:
            list of AndroidDevice instances.
        """
        dl = []
        resp = self._message(b"host:devices-l")
        for line in resp.splitlines():
            dl.append(_device_factory(line))
        return dl

    def forward(self, serial, hostport, devport):
        """Tell server to start forwarding TCP ports.
        """
        msg = b"host-serial:%b:forward:tcp:%d;tcp:%d" % (serial.encode("ascii"),
                                                         hostport, devport)
        get_kernel().run(_command_transact(self._conn, msg))

    def list_forward(self):
        """Return a list of currently forwarded ports.

        Returns:
            Tuple of (serial, host_port, device_port).
        """
        resp = self._message(b"host:list-forward")
        fl = []
        for line in resp.splitlines():
            # <serial> " " <local> " " <remote> "\n"
            serno, host_port, remote_port = line.split()
            fl.append((serno.decode("ascii"),
                       int(host_port.split(b":")[1]),
                       int(remote_port.split(b":")[1])))
        return fl

    def reconnect_offline(self):
        self._message(b"host:reconnect-offline")

    def reconnect(self, serial):
        self._message(b"host-serial:%b:reconnect" % (serial.encode("ascii"),))
        while self.get_state(serial) is None:
            timers.nanosleep(1.1)

    @property
    def server_version(self):
        """The server's version number."""
        resp = self._message(b"host:version")
        return int(resp, 16)


def getAsyncAndroidDeviceClient(serial, host="localhost", port=ADB_PORT):
    """Get initialized _AsyncAndroidDeviceClient object from sync code.
    """
    return get_kernel().run(AsyncAndroidDeviceClient(serial, host, port))


async def AsyncAndroidDeviceClient(serial, host="localhost", port=ADB_PORT):
    """Get initialized _AsyncAndroidDeviceClient instance from async code."""
    ac = _AsyncAndroidDeviceClient(serial, host, port)
    await ac._init()
    return ac


class _AsyncAndroidDeviceClient:
    """An active adb client per device.

    For device specific operations.
    For use in asynchronous event loops.
    """
    def __init__(self, serial, host="localhost", port=ADB_PORT):
        self.serial = serial.encode("ascii")
        self._conn = AdbConnection(host=host, port=port)

    async def _init(self):
        await self._conn.open()
        await self.get_features()

    async def _message(self, msg):
        return await _transact(self._conn, msg)

    async def get_features(self):
        msg = b"host-serial:%b:features" % (self.serial,)
        resp = await self._message(msg)
        self.features = resp.decode("ascii")
        return self.features

    async def close(self):
        await self._conn.close()

    async def open(self):
        await self._conn.open()

    async def get_state(self):
        msg = b"host-serial:%b:get-state" % (self.serial,)
        resp = await self._message(msg)
        return resp.decode("ascii")

    async def reboot(self):
        await _connect_command(self.serial, self._conn, b"reboot:")

    async def remount(self):
        resp = await _special_command(self.serial, self._conn, b"remount:")
        return resp.decode("ascii")

    async def root(self):
        resp = await _special_command(self.serial, self._conn, b"root:")
        await sleep(3)  # adbd needs some time to initialize
        return resp.decode("ascii")

    async def unroot(self):
        resp = await _special_command(self.serial, self._conn, b"unroot:")
        await sleep(3)  # adbd needs some time to initialize
        return resp.decode("ascii")

    async def forward(self, hostport, devport):
        """Tell server to start forwarding TCP ports.
        """
        msg = b"host-serial:%b:forward:tcp:%d;tcp:%d" % (self.serial,
                                                         hostport, devport)
        await _command_transact(self._conn, msg)

    async def kill_forward(self, hostport):
        """Tell server to remove forwarding TCP ports.
        """
        msg = b"host-serial:%b:killforward:tcp:%d" % (self.serial, hostport)
        await _command_transact(self._conn, msg)

    async def kill_forward_all(self):
        """Tell server to remove all forwarding TCP ports.
        """
        msg = b"host-serial:%b:killforward-all" % (self.serial,)
        await _command_transact(self._conn, msg)

    async def list_forward(self):
        """Return a list of currently forwarded ports.

        Returns:
            Tuple of (host_port, device_port).
        """
        msg = b"host-serial:%b:list-forward" % (self.serial,)
        resp = await self._message(msg)
        fl = []
        for line in resp.splitlines():
            # <serial> " " <local> " " <remote> "\n"
            serno, host_port, remote_port = line.split()
            if serno == self.serial:
                fl.append((int(host_port.split(b":")[1]),
                           int(remote_port.split(b":")[1])))
        return fl

    async def wait_for(self, state: str):
        """Wait for device to be in a particular state.

        State must be one of {"any", "bootloader", "device", "recovery", "sideload"}
        """
        if state not in {"any", "bootloader", "device", "recovery", "sideload"}:
            raise ValueError("Invalid state to wait for.")
        msg = b"host-serial:%b:wait-for-usb-%b" % (self.serial, state.encode("ascii"))
        await _command_transact(self._conn, msg)

    async def command(self, cmdline, usepty=False):
        """Run a non-interactive shell command.

        Uses ring buffers to collect outputs to avoid a runaway device command
        from filling host memory. However, this might possibly truncate output.

        Returns:
            stdout (string): output of command
            stderr (string): error output of command
            exitstatus (ExitStatus): the exit status of the command.
        """
        if self.features is None:
            await self.get_features()
        if "shell_v2" not in self.features:
            raise AdbCommandFail("Only shell v2 protocol currently supported.")
        cmdline, name = _fix_command_line(cmdline)
        await _start_shell(self.serial, self._conn, usepty, cmdline)
        sp = ShellProtocol(self._conn.socket)
        stdout = ringbuffer.RingBuffer(MAX_PAYLOAD)
        stderr = ringbuffer.RingBuffer(MAX_PAYLOAD)
        resp = await sp.run(None, stdout, stderr)
        await self._conn.close()
        rc = resp[0]
        if rc & 0x80:
            rc = -(rc & 0x7F)
        return (stdout.read().decode("utf8"),
                stderr.read().decode("utf8"),
                exitstatus.ExitStatus(
                    None,
                    name="{}@{}".format(name, self.serial.decode("ascii")),
                    returncode=rc)
                )

    async def list(self, name, coro_cb):
        sp = SyncProtocol(self.serial)
        await sp.connect_with(self._conn)
        await sp.list(name, coro_cb)
        await sp.quit()
        await self._conn.close()

    async def stat(self, path):
        """stat a remote file or directory.

        Return os.stat_result with attributes from remote path.
        """
        sp = SyncProtocol(self.serial)
        await sp.connect_with(self._conn)
        try:
            st = await sp.stat(path)
        finally:
            await sp.quit()
            await self._conn.close()
        return st

    async def push(self, localfiles: list, remotepath: str, sync: bool = False):
        """Push a list of local files to remote file or directory.
        """
        sp = SyncProtocol(self.serial)
        await sp.connect_with(self._conn)
        try:
            resp = await sp.push(localfiles, remotepath, sync)
        finally:
            await sp.quit()
            await self._conn.close()
        return resp

    async def start(self, cmdline, stdoutstream, stderrstream):
        """Start a process on device with the shell protocol.

        Returns a curio Task object wrapping the ShellProtocol run.
        """
        cmdline, name = _fix_command_line(cmdline)
        await _start_shell(self.serial, self._conn, False, cmdline)
        sp = ShellProtocol(self._conn.socket)
        return await spawn(sp.run(None, stdoutstream, stderrstream))

    async def spawn(self, cmdline):
        """Start a process on device in raw mode.

        Return:
            DeviceProcess with active connection.
        """
        cmdline, name = _fix_command_line(cmdline)
        logging.info("adb.spawn({})".format(cmdline))
        sock = await _start_exec(self.serial, self._conn, cmdline)
        return DeviceProcess(sock, name)

    async def install(self, apkfile, allow_test=True, installer=None,
                      onsdcard=False, onflash=False, allow_downgrade=True,
                      grant_all=True):
        """Install an APK.

        Performs a streaming installation.  Returns True if Success.
        """
        # TODO(dart) other options
        st = os.stat(apkfile)  # TODO(dart) fix potential long blocker
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("The apkfile must be a regular file.")
        cmdline = ["cmd", "package", "install"]
        if allow_test:
            cmdline.append("-t")
        if installer is not None:
            cmdline.extend(["-i", str(installer)])
        if onsdcard:
            cmdline.append("-s")
        if onflash:
            cmdline.append("-f")
        if allow_downgrade:
            cmdline.append("-d")
        if grant_all:
            cmdline.append("-g")
        cmdline.extend(["-S", str(st.st_size)])
        cmdline, name = _fix_command_line(cmdline)
        sock = await _start_exec(self.serial, self._conn, cmdline)
        p = DeviceProcess(sock, name)
        del sock
        async with streams.aopen(apkfile, "rb") as afo:
            await p.copy_from(afo)
        status_response = await p.read(4096)
        await p.close()
        return b'Success' in status_response
    # TODO(dart) install sessions

    async def package(self, cmd, *args, user=None, **kwargs):
        """Manage packages.

        Equivalent of 'pm' command.
        """
        cmdline = ['cmd', 'package']
        if user is not None:
            cmdline.append("--user")
            cmdline.append(str(user))
        cmdline.append(cmd)
        cmdline.extend(str(arg) for arg in args)
        for opt, optarg in kwargs.items():
            cmdline.append("--" + opt)
            if optarg not in (None, True):
                cmdline.append(str(optarg))
        out, err, es = await self.command(cmdline)
        if not es:
            raise AdbCommandFail(err)
        return out

    async def reconnect(self):
        msg = b"host-serial:%b:reconnect" % (self.serial,)
        await _command_transact(self._conn, msg)
        await self._conn.close()
        await self._init()

    async def logcat_clear(self):
        """Clear logcat buffer."""
        stdout, stderr, es = await self.command(["logcat", "-c"])
        if not es:
            raise AdbCommandFail("Didn't clear logcat")

    async def logcat(self, stdoutstream, stderrstream, format="threadtime",
                     buffers="default", modifiers=None, binary=False,
                     regex=None, dump=False, logtags=""):
        """Coroutine for streaming logcat output to the provided file-like
        streams.

        Args:
            stdout, stderr: file-like object to write log events to.
            binary: bool output binary format if True.
            regex: A Perl compatible regular expression to match messages against.
            format: str of one of the following:
                    "brief", "long", "process", "raw", "tag", "thread",
                    "threadtime", "time".
            buffers: list or comma separated string of:
                     'main', 'system', 'radio', 'events', 'crash', 'default' or 'all'
            modifiers: str of one or more of:
                       epoch", "monotonic", "uid", "usec", "UTC", "year", "zone"
            logcats: str of space separated filter expressions.
        """
        logtags = os.environ.get("ANDROID_LOG_TAGS", logtags)
        cmdline = ['exec', 'logcat']
        # buffers
        if isinstance(buffers, str):
            buffers = buffers.split(",")
        for bufname in buffers:
            cmdline.extend(["-b", bufname])
        if binary:
            cmdline.append("-B")
        if regex:
            cmdline.extend(["-e", regex])
        if dump:
            cmdline.append("-d")
        # output format
        if format not in {"brief", "long", "process", "raw", "tag",
                          "thread", "threadtime", "time"}:
            raise ValueError("Bad format type.")
        if modifiers:
            if isinstance(modifiers, str):
                modifiers = modifiers.split(",")
            for modifier in modifiers:
                if modifier in {"epoch", "monotonic", "uid", "usec", "UTC",
                                "year", "zone"}:
                    format += ("," + modifier)
                else:
                    raise ValueError("Invalid logcat format modifier")
        cmdline.extend(["-v", format])
        # logtags
        if logtags:
            logtags = logtags.replace('"', '\\"')
            cmdline.extend(logtags.split())
        # go!
        cmdline, _ = _fix_command_line(cmdline)
        await _start_shell(self.serial, self._conn, False, cmdline)
        sp = ShellProtocol(self._conn.socket)
        await sp.run(None, stdoutstream, stderrstream)


class AndroidDeviceClient:
    """An active adb client per device.

    For synchronous (blocking) style code.
    """
    def __init__(self, serial, host="localhost", port=ADB_PORT):
        self._aadb = _AsyncAndroidDeviceClient(serial, host, port)
        self.open()
        self.features = self.get_features()

    def close(self):
        get_kernel().run(self._aadb.close())

    def open(self):
        get_kernel().run(self._aadb.open())

    @property
    def serial(self):
        return self._aadb.serial

    @property
    def async_client(self):
        return self._aadb

    def get_features(self):
        return get_kernel().run(self._aadb.get_features())

    def get_state(self):
        return get_kernel().run(self._aadb.get_state())

    def reboot(self):
        """Reboot the device."""
        return get_kernel().run(self._aadb.reboot())

    def remount(self):
        """Remount filesystem read-write."""
        return get_kernel().run(self._aadb.remount())

    def root(self):
        """Become root on the device."""
        return get_kernel().run(self._aadb.root())

    def unroot(self):
        """Become non-root on the device."""
        return get_kernel().run(self._aadb.unroot())

    def forward(self, hostport, devport):
        """Tell server to start forwarding TCP ports.
        """
        return get_kernel().run(self._aadb.forward(hostport, devport))

    def kill_forward(self, hostport):
        """Tell server to remove forwarding TCP ports.
        """
        return get_kernel().run(self._aadb.kill_forward(hostport))

    def list_forward(self):
        """Get a list of currently forwarded ports."""
        return get_kernel().run(self._aadb.list_forward())

    def wait_for(self, state: str):
        """Wait for device to be in a particular state.

        State must be one of {"any", "bootloader", "device", "recovery", "sideload"}
        """
        return get_kernel().run(self._aadb.wait_for(state))

    def command(self, cmdline, usepty=False):
        """Run a non-interactive shell command.

        Uses ring buffers to collect outputs to avoid a runaway device command
        from filling host memory. However, this might possibly truncate output.

        Returns:
            stdout (string): output of command
            stderr (string): error output of command
            exitstatus (ExitStatus): the exit status of the command.
        """
        return get_kernel().run(self._aadb.command(cmdline, usepty))

    def spawn(self, cmdline):
        """Start a process on device in raw mode.

        Return:
            DeviceProcess with active connection.
        """
        return get_kernel().run(self._aadb.spawn(cmdline))

    def install(self, apkfile, **kwargs):
        """Install an APK.

        Default flags are best for testing, but you can override. See asyn
        method.
        """
        coro = self._aadb.install(apkfile, **kwargs)
        return get_kernel().run(coro)

    def package(self, cmd, *args, user=None, **kwargs):
        """Manage packages.

        Equivalent of 'pm' command.
        """
        coro = self._aadb.package(cmd, *args, user=user, **kwargs)
        return get_kernel().run(coro)

    def list(self, name, cb):
        """Perform a directory listing.

        Arguments:
            name: str, name of directory
            cb: callable with signature cb(os.stat_result, filename)
        """
        async def acb(stat, path):
            await block_in_thread(cb, stat, path)
        coro = self._aadb.list(name, acb)
        return get_kernel().run(coro)

    def stat(self, path: str):
        """stat a remote file or directory.

        Return os.stat_result with attributes from remote path.
        """
        coro = self._aadb.stat(path)
        return get_kernel().run(coro)

    def push(self, localfiles: list, remotepath: str, sync: bool = False):
        """Push a list of local files to remote file or directory.
        """
        coro = self._aadb.push(localfiles, remotepath, sync)
        return get_kernel().run(coro)

    def reconnect(self):
        """Reconnect from device side."""
        return get_kernel().run(self._aadb.reconnect())

    def logcat_clear(self):
        """Clear logcat buffer."""
        return get_kernel().run(self._aadb.logcat_clear())

    async def logcat(self, stdoutstream, stderrstream, format="threadtime",
                     buffers="default", modifiers=None, binary=False,
                     regex=None, logtags=""):
        """Coroutine for streaming logcat output to the provided file-like
        streams.
        """
        await self._aadb.logcat(stdoutstream, stderrstream, format=format,
                                buffers=buffers, modifiers=modifiers,
                                binary=binary, regex=regex, logtags=logtags)


class DeviceProcess:
    """Represents an attached process on the device.
    """
    def __init__(self, asocket, name):
        self.socket = asocket
        self.name = name

    def __str__(self):
        return "DeviceProcess running {!r}".format(self.name)

    async def copy_to(self, otherfile):
        """Copy output from this process to another file stream."""
        while True:
            data = await self.socket.recv(MAX_PAYLOAD)
            if not data:
                break
            await otherfile.write(data)

    async def copy_from(self, otherfile):
        """Copy output from another file stream to this process."""
        while True:
            data = await otherfile.read(MAX_PAYLOAD)
            if not data:
                break
            await self.socket.sendall(data)

    async def read(self, amt):
        return await self.socket.recv(amt)

    async def write(self, data):
        return await self.socket.sendall(data)

    async def close(self):
        if self.socket is not None:
            await self.socket.close()
            self.socket = None

    def sync_close(self):
        return get_kernel().run(self.close)


def _fix_command_line(cmdline):
    """Fix the command.

    If a list, quote the components if required.
    Return encoded command line as bytes and the command base name.
    """
    if isinstance(cmdline, list):
        name = cmdline[0]
        cmdline = " ".join('"{}"'.format(s) if " " in s else str(s) for s in cmdline)
    else:
        name = cmdline.split()[0]
    return cmdline.encode("utf8"), name


# Perform shell request, connection stays open
async def _start_shell(serial, conn, usepty, cmdline):
    tpmsg = b"host:transport:%b" % serial
    msg = b"shell,%b:%b" % (b",".join([b"v2",
                                       b"TERM=%b" % os.environb[b"TERM"],
                                       b"pty" if usepty else b"raw"]),
                            cmdline)
    await conn.open()
    await conn.message(tpmsg, expect_response=False)
    await conn.message(msg, expect_response=False)


async def _start_exec(serial, conn, cmdline):
    tpmsg = b"host:transport:%b" % serial
    msg = b"exec:%b" % (cmdline,)
    await conn.open()
    await conn.message(tpmsg, expect_response=False)
    await conn.message(msg, expect_response=False)
    sock = conn.socket.dup()
    await conn.close()
    return sock


# Send command to specific device with orderly shutdown
async def _connect_command(serial, conn, msg):
    tpmsg = b"host:transport:%b" % serial
    await conn.open()
    await conn.message(tpmsg, expect_response=False)
    await conn.message(msg, expect_response=False)
    await conn.close()


# Root command transaction is special since device adbd restarts.
async def _special_command(serial, conn, cmd):
    tpmsg = b"host:transport:%b" % serial
    await conn.open()
    await conn.message(tpmsg, expect_response=False)
    await conn.message(cmd, expect_response=False)
    resp = await conn.socket.recv(4096)
    await conn.close()
    return resp


class ShellProtocol:
    """Implement the shell protocol v2."""
    IDSTDIN = 0
    IDSTDOUT = 1
    IDSTDERR = 2
    IDEXIT = 3
    CLOSESTDIN = 4
    # Window size change (an ASCII version of struct winsize).
    WINDOWSIZECHANGE = 5
    # Indicates an invalid or unknown packet.
    INVALID = 255

    def __init__(self, socket):
        self._sock = socket
        self._header = struct.Struct(b"<BI")
        self._winsize = None

    async def run(self, inbuf, outbuf, errbuf):
        while True:
            tl = await self._sock.recv(5)
            msgtype, msglen = self._header.unpack(tl)
            if msgtype == 0:
                pass
            elif msgtype == 1:
                data = await self._sock.recv(msglen)
                outbuf.write(data)
            elif msgtype == 2:
                data = await self._sock.recv(msglen)
                errbuf.write(data)
            elif msgtype == 3:
                data = await self._sock.recv(msglen)
                return data
            elif msgtype == 4:
                pass  # TODO
            elif msgtype == 5:
                data = await self._sock.recv(msglen)
                self._winsize = data
            else:
                raise AdbProtocolError("Unhandled shell protocol message type.")


class SyncProtocol:
    """Implementation of Android SYNC protocol.

    Only recent devices are supported.
    """

    mkid = lambda code: int.from_bytes(code, byteorder='little')  # noqa
    ID_LSTAT_V1 = mkid(b'STAT')
    ID_STAT_V2 = mkid(b'STA2')
    ID_LSTAT_V2 = mkid(b'LST2')
    ID_LIST = mkid(b'LIST')
    ID_SEND = mkid(b'SEND')
    ID_RECV = mkid(b'RECV')
    ID_DENT = mkid(b'DENT')
    ID_DONE = mkid(b'DONE')
    ID_DATA = mkid(b'DATA')
    ID_OKAY = mkid(b'OKAY')
    ID_FAIL = mkid(b'FAIL')
    ID_QUIT = mkid(b'QUIT')
    del mkid

    SYNC_DATA_MAX = 65536
    SYNCMSG_DATA = struct.Struct("<II")  # id, size
    # id; mode; size; time; namelen;
    SYNCMSG_DIRENT = struct.Struct("<IIIII")
    # id; error; dev; ino; mode; nlink; uid; gid; size; atime; mtime; ctime;
    SYNCMSG_STAT_V2 = struct.Struct("<IIQQIIIIQqqq")
    SYNCMSG_STATUS = struct.Struct("<II")  # id, msglen

    def __init__(self, serial):
        self.serial = serial
        self.socket = None

    async def connect_with(self, adbconnection):
        tpmsg = b"host:transport:%b" % self.serial
        msg = b"sync:"
        await adbconnection.open()
        await adbconnection.message(tpmsg, expect_response=False)
        await adbconnection.message(msg, expect_response=False)
        self.socket = adbconnection.socket

    async def quit(self):
        msg = SyncProtocol.SYNCMSG_STATUS.pack(SyncProtocol.ID_QUIT, 0)
        self.socket.sendall(msg)

    async def send_request(self, protoid: int, path_and_mode: str):
        path_and_mode = path_and_mode.encode("utf-8")
        length = len(path_and_mode)
        if length > 1024:
            raise ValueError("Can't send message > 1024")
        hdr = SyncProtocol.SYNCMSG_DATA.pack(protoid, length)
        await self.socket.sendall(hdr + path_and_mode)

    async def list(self, path, cb_coro):
        """List a directory on device."""
        await self.send_request(SyncProtocol.ID_LIST, path)
        while True:
            resp = await self.socket.recv(SyncProtocol.SYNCMSG_DIRENT.size)
            msgid, mode, size, time, namelen = SyncProtocol.SYNCMSG_DIRENT.unpack(resp)
            if msgid == SyncProtocol.ID_DONE:
                return True
            if msgid != SyncProtocol.ID_DENT:
                return False
            name = await self.socket.recv(namelen)
            stat = os.stat_result((mode, None, None, None, 0, 0, size, None, float(time), None))
            await cb_coro(stat, name.decode("utf-8"))

    async def stat(self, remotepath):
        """Stat a path."""
        s = SyncProtocol.SYNCMSG_STAT_V2
        await self.send_request(SyncProtocol.ID_STAT_V2, remotepath)
        resp = await self.socket.recv(s.size)
        stat_id, err, dev, ino, mode, nlink, uid, gid, size, atime, mtime, ctime = s.unpack(resp)
        if stat_id == SyncProtocol.ID_STAT_V2:
            if err != 0:
                raise OSError(err, errno.errorcode[err], remotepath)
            sr = os.stat_result((mode, ino, dev, nlink, uid, gid, size,
                                 float(atime), float(mtime), float(ctime),  # floats
                                 # int nanoseconds, but not really
                                 atime * 1e9, mtime * 1e9, ctime * 1e9))
            return sr
        else:
            raise AdbProtocolError("SyncProtocol: invalid response type.")

    async def push(self, localfiles, remotepath, sync=False):
        """Push files to device destination."""
        try:
            dest_st = await self.stat(remotepath)
        except FileNotFoundError:
            dst_exists = False
            dst_isdir = False
        else:
            dst_exists = True
            if stat.S_ISDIR(dest_st.st_mode):
                dst_isdir = True
            elif stat.S_ISREG(dest_st.st_mode):
                dst_isdir = False
            else:
                raise ValueError("push: destination is not a directory or "
                                 "regular file")
        if not dst_isdir:
            if len(localfiles) > 1:
                raise ValueError("push: destination is not a dir when copying "
                                 "multiple files.")
            if dst_exists:
                raise ValueError("push: destination exists")
        for localfile in localfiles:
            local_st = os.stat(localfile)

            if stat.S_ISDIR(local_st.st_mode):
                rpath = os.path.join(remotepath, os.path.basename(localfile))
                await self._copy_local_dir_remote(localfile, rpath, sync)

            if stat.S_ISREG(local_st.st_mode):
                if dst_isdir:
                    rpath = os.path.join(remotepath, os.path.basename(localfile))
                # If synchronize requested, just stat remote and return if size
                # and mtime are equal.
                if sync:
                    try:
                        dst_stat = await self.stat(rpath)
                    except OSError:
                        pass
                    else:
                        if (local_st.st_size == dst_stat.st_size and
                            local_st.st_mtime == dst_stat.st_mtime):
                            return
                await self._sync_send(localfile.encode("utf8"),
                                      rpath.encode("utf8"),
                                      local_st)

    async def pull(self, remotepath, localpath):
        pass  # TODO(dart)

    async def _sync_send(self, src_path, dst_path, local_st):
        if stat.S_ISLNK(local_st.st_mode):
            raise NotImplementedError("TODO(dart)")
        if local_st.st_size < SyncProtocol.SYNC_DATA_MAX:
            with open(src_path, "rb") as fo:
                data = fo.read()
            path_and_mode = b"%s,%d" % (dst_path, local_st.st_mode)
            return await self._send_small_file(path_and_mode, data, int(local_st.st_mtime))
        else:
            return await self._send_large_file(src_path, dst_path, local_st)

    async def _send_small_file(self, path_and_mode, data, mtime):
        sm = SyncProtocol.SYNCMSG_DATA
        buf = ringbuffer.RingBuffer(SyncProtocol.SYNC_DATA_MAX << 1)  # big enough to not wrap
        buf.write(sm.pack(SyncProtocol.ID_SEND, len(path_and_mode)))
        buf.write(path_and_mode)
        buf.write(sm.pack(SyncProtocol.ID_DATA, len(data)))
        buf.write(data)
        buf.write(sm.pack(SyncProtocol.ID_DONE, mtime))
        await self.socket.sendall(buf.read())
        return await self._copy_done()

    async def _send_large_file(self, src_path, dst_path, local_st):
        sm = SyncProtocol.SYNCMSG_DATA
        buf = ringbuffer.RingBuffer(SyncProtocol.SYNC_DATA_MAX << 1)

        path_and_mode = b"%s,%d" % (dst_path, local_st.st_mode)
        buf.write(sm.pack(SyncProtocol.ID_SEND, len(path_and_mode)))
        buf.write(path_and_mode)
        await self.socket.sendall(buf.read())

        buf.clear()
        chunksize = SyncProtocol.SYNC_DATA_MAX - sm.size
        with open(src_path, "rb") as fo:
            while True:
                chunk = fo.read(chunksize)
                if not chunk:
                    break
                buf.write(sm.pack(SyncProtocol.ID_DATA, len(chunk)))
                buf.write(chunk)
                await self.socket.sendall(buf.read())

        buf.clear()
        buf.write(sm.pack(SyncProtocol.ID_DONE, int(local_st.st_mtime)))
        await self.socket.sendall(buf.read())
        return await self._copy_done()

    async def _copy_done(self):
        sm = SyncProtocol.SYNCMSG_STATUS
        raw = await self.socket.recv(sm.size)
        msg_id, msg_len = sm.unpack(raw)
        if msg_id == SyncProtocol.ID_OKAY:
            return True
        if msg_id == SyncProtocol.ID_FAIL:
            msg = await self.socket.recv(msg_len)
            raise AdbCommandFail(
                "large file copy not OKAY: {!r}".format(msg.decode("utf8")))

    async def _copy_local_dir_remote(self, localfile, remotepath, sync):
        raise NotImplementedError("TODO(dart)")


class LogcatMessage:
    """An Android log message.

    Attributes:
        tag: (str) The tag of the message as set by the sender.
        priority: (LogPriority) The priority of the message.
        message: (str) The text message given by the caller.
        timestamp: (float) The devices' time that the message was created.
        pid: (int) The process ID of sending process.
        tid: (int) The thread ID of sending thread.
        lid: (int) The log ID.
        uid: (int) The user ID of the process that sent this message.
    """
    def __init__(self, pid, tid, sec, nsec, lid, uid, msg):
        self.pid = pid
        self.tid = tid
        self.timestamp = float(sec) + (nsec / 1e9)
        self.lid = LogId(lid)
        self.uid = uid
        try:
            self.priority = LogPriority(msg[0])
        except ValueError:
            self.priority = LogPriority.UNKNOWN
        tagend = msg.find(b'\x00')
        if tagend > 0:
            self.tag = (msg[1:tagend]).decode("ascii")
            self.message = (msg[tagend + 1:-1]).decode("utf8")
        else:
            self.tag = None
            self.message = msg.decode("utf8")

    def __str__(self):
        return "{:11.6f} {}:{} {}|{}¦{}".format(self.timestamp, self.pid, self.tid,
                                                self.tag, self.priority.name,
                                                self.message)


class LogcatHandler:
    """Host side logcat handler that receives logcat messages in binary mode
    over raw connection.
    """

    LOGCAT_MESSAGE = struct.Struct("<HHiIIIII")  # logger_entry_v4
    #  uint16_t len;       length of the payload
    #  uint16_t hdr_size;  sizeof(struct logger_entry_v4)
    #  int32_t pid;        generating process's pid
    #  uint32_t tid;       generating process's tid
    #  uint32_t sec;       seconds since Epoch
    #  uint32_t nsec;      nanoseconds
    #  uint32_t lid;       log id of the payload, bottom 4 bits currently
    #  uint32_t uid;       generating process's uid
    #  char msg[0];        the entry's payload

    def __init__(self, aadb):
        self._aadb = aadb

    def clear(self):
        """Clear logcat buffers."""
        return get_kernel().run(self._aadb.logcat_clear())

    def dump(self):
        """Dump logs to stdout until interrupted."""
        return get_kernel().run(self._dump())

    async def _dump(self):
        ac = self._aadb
        signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
        await ac.logcat_clear()
        proc = await ac.spawn('logcat -B -b default')
        task = await spawn(self._read_and_dump(proc, streams.FileStream(sys.stdout.buffer)))
        await signalset.wait()
        await task.cancel()
        await proc.close()

    async def _read_and_dump(self, proc, out):
        while True:
            lm = await self._read_one(proc)
            await out.write(str(lm).encode("utf8"))
            await out.write(b'\n')

    async def _read_one(self, proc):
        s = self.LOGCAT_MESSAGE
        rawhdr = await proc.read(s.size)
        payload_len, hdr_size, pid, tid, sec, nsec, lid, uid = s.unpack(rawhdr)
        payload = await proc.read(payload_len)
        return LogcatMessage(pid, tid, sec, nsec, lid, uid, payload)

    def dump_to(self, localfile, logtags=None):
        """Dump all current logs to a file, in binary format."""
        return get_kernel().run(self._dump_to(localfile, logtags))

    async def _dump_to(self, localfile, logtags):
        cmdline = ['logcat', '-d', '-B', '-b', 'default']
        if logtags:
            cmdline.extend(logtags.split())
        proc = await self._aadb.spawn(cmdline)
        with open(localfile, "wb") as fo:
            await proc.copy_to(streams.FileStream(fo))
        await proc.close()

    def watch_for(self, tag=None, priority=None, text=None, timeout=90):
        """Watch for first occurence of a particular set of tag, priority, or
        message text.

        If tag is given watch for first of that tag.
        If tag and priority is given watch for tag only with that priority.
        if tag and text is given watch for tag with the given text in the
        message part.
        If text is given look for first occurence of text in message part.
        """
        if tag is None and text is None:
            raise ValueError("watch_for: must supply one or both of 'tag' or "
                             "'text' parameters.")
        return get_kernel().run(self._watch_for(tag, priority, text, timeout))

    async def _watch_for(self, tag, priority, text, timeout):
        lm = None
        ac = self._aadb
        await ac.logcat_clear()
        proc = await ac.spawn('logcat -B -b default')
        try:
            async with timeout_after(timeout):
                while True:
                    new = await self._read_one(proc)
                    if tag and tag == new.tag:
                        if priority is not None:
                            if new.priority == priority:
                                lm = new
                                break
                        else:
                            lm = new
                            break
                        if text is not None:
                            if text in new.message:
                                lm = new
                                break
                    if text and text in new.message:
                        lm = new
                        break
        except TaskTimeout:
            pass
        await proc.close()
        return lm


class LogcatFileReader:
    """Read and decode binary logcat files.

    These are usually obtained from a LogcatHandler dump_to.
    """
    LOGCAT_MESSAGE = struct.Struct("<HHiIIIII")  # logger_entry_v4

    def __init__(self, filename):
        self.filename = os.fspath(filename)

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self.filename)

    def search(self, tag=None, priority=None, regex=None):
        """Search the log for tag or regular expression in text.

        If tag is given, match on tag. If priority is also given, must match
        both tag and priority.
        IF a Regex object is given, match the message body only with that regex.
        If both tag and regex given, both must match. If all given, all must
        match.

        Yield LogcatMessage and MatchObject on matches. MatchObject will be None
        if regex is not given.
        """
        if tag is None and regex is None:
            raise ValueError("At least one of tag or regex must be supplied.")
        with open(self.filename, "rb") as lfo:
            self._sync_file(lfo)
            while True:
                lm = self._read_one(lfo)
                if lm is None:
                    break
                if tag and tag == lm.tag:
                    if priority is not None:
                        if lm.priority == priority:
                            if regex is not None:
                                mo = regex.search(lm.message)
                                if mo:
                                    yield lm, mo
                            else:
                                yield lm, None
                    else:
                        if regex is not None:
                            mo = regex.search(lm.message)
                            if mo:
                                yield lm, mo
                        else:
                            yield lm, None
                if regex is not None:
                    mo = regex.search(lm.message)
                    if mo:
                        yield lm, mo

    def find_first_tag(self, tag):
        """Find first occurence of a tag.
        """
        for lm, _ in self.search(tag=tag):
            return lm

    def dump(self, tag=None):
        """Write deocded log to stdout."""
        return self.dump_to(sys.stdout.buffer, tag=tag)

    def dump_to(self, fo, tag=None):
        """Dump decoded text to a file-like object."""
        with open(self.filename, "rb") as lfo:
            self._sync_file(lfo)
            lines = self._dump(lfo, fo, tag)
        return lines

    def _dump(self, fo, out, tag):
        lines = 0
        try:
            while True:
                lm = self._read_one(fo)
                if lm is None:
                    break
                if tag and tag != lm.tag:
                    continue
                lines += 1
                out.write(str(lm).encode("utf8"))
                out.write(b'\n')
        except BrokenPipeError:
            pass
        return lines

    def dump_to_file(self, localfile, tag=None):
        with open(localfile, "wb") as fo:
            lines = self.dump_to(fo, tag)
        return lines

    def _read_one(self, fo):
        s = self.LOGCAT_MESSAGE
        rawhdr = fo.read(s.size)
        if len(rawhdr) < s.size:
            return None
        payload_len, hdr_size, pid, tid, sec, nsec, lid, uid = s.unpack(rawhdr)
        payload = fo.read(payload_len)
        return LogcatMessage(pid, tid, sec, nsec, lid, uid, payload)

    def _sync_file(self, fo):
        # in case of cruft at start of file.
        # The header size is fixed, so will always have the same value, and
        # hdr_size field equals LOGCAT_MESSAGE size. Look for that.
        header_peek = struct.Struct("<HH")
        while True:
            payload_len, hdr_size = header_peek.unpack(fo.read(header_peek.size))
            if hdr_size == self.LOGCAT_MESSAGE.size:
                fo.seek(-header_peek.size, 1)
                return
            else:
                fo.seek(-(header_peek.size - 1), 1)


class AndroidDevice:
    """Information about attached Android device.

    No connection necessary.
    """

    def __init__(self, serial, product, model, device, state):
        self.type = "phone"
        self.serial = serial
        self.product = product
        self.model = model
        self.device = device
        self.state = state

    def __repr__(self):
        return ("AndroidDevice("
                "serial={!r}, product={!r}, model={!r}, device={!r}, state={!r})".format(
                    self.serial, self.product, self.model, self.device, self.state))


# b'HTxxxserial device usb:1-1.1 product:marlin model:Pixel_XL device:marlin\n'
def _device_factory(line):
    parts = line.decode("ascii").split()
    serial = parts[0]
    state = parts[1]
    if state == "device":
        product = parts[3].partition(":")[2]
        model = parts[4].partition(":")[2]
        device = parts[5].partition(":")[2]
        return AndroidDevice(serial, product, model, device, state)
    else:
        return AndroidDevice(serial, None, None, None, state)


if __name__ == "__main__":
    from devtest import debugger
    debugger.autodebug()
    start_server()
    print("Test AdbClient:")
    c = AdbClient()
    print("  Server version:", c.server_version)
    for devinfo in c.get_device_list():
        print("    ", devinfo)
    print("Forwards:", c.list_forward())
    c.close()
    del c

    print("Test AndroidDeviceClient:")
    ac = AndroidDeviceClient(devinfo.serial)
    ac.wait_for("device")
    print("  features:", ac.features)
    print("  state:", ac.get_state())
    print("  running 'ls /sdcard':")
    stdout, stderr, es = ac.command(["ls", "/sdcard"])
    print("    ", es)
    print("    stdout:", repr(stdout))
    print("    stderr:", repr(stderr))
    print("forward list:")
    print(repr(ac.list_forward()))
    ac.close()
    del ac

    # Test async with logcat. ^C to stop it.
    async def dostuff():
        ac = await AsyncAndroidDeviceClient(devinfo.serial)

        stdout, stderr, es = await ac.command(["ls", "/sdcard"])
        print("    ", es)
        print("    stdout:", repr(stdout))
        print("    stderr:", repr(stderr))

        fl = await ac.list_forward()
        print("Forward list:")
        print(repr(fl))
        print("Logcat:")
        signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
        await ac.wait_for("device")
        try:
            await ac.logcat_clear()
            task = await spawn(ac.logcat(sys.stdout.buffer, sys.stdout.buffer,
                                         buffers="kernel,main",
                                         format="long", modifiers="epoch,usec",
                                         binary=False,
                                         logtags=" ".join(sys.argv[1:])))
            await signalset.wait()
            await task.cancel()
        finally:
            await ac.close()
        await ac.close()

    kern = get_kernel()
    kern.run(dostuff)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
