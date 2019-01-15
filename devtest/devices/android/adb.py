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
import struct

from devtest import timers
from devtest import ringbuffer
from devtest.io import socket
from devtest.io import streams
from devtest.os import process
from devtest.os import procutils
from devtest.os import exitstatus
from devtest.io.reactor import get_kernel, spawn, block_in_thread, sleep


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
        if not self._conn.isopen():
            raise Error("Operation on a closed device client.")
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
        await self._conn.close()

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

    async def reconnect(self):
        msg = b"host-serial:%b:reconnect" % (self.serial,)
        await _command_transact(self._conn, msg)
        await self._conn.close()
        await self._init()

    async def logcat(self, stdoutstream, stderrstream, longform=False, logtags=""):
        """Coroutine for streaming logcat output to the provided file-like
        streams.
        """
        logtags = os.environ.get("ANDROID_LOG_TAGS", logtags)
        logtags = logtags.replace('"', '\\"')
        longopt = "-v long" if longform else ""
        cmdline = 'export ANDROID_LOG_TAGS="{}"; exec logcat {}'.format(logtags,
                                                                        longopt)
        cmdline = cmdline.encode("utf8")
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

    def install(self, apkfile, **kwargs):
        """Install an APK.

        Default flags are best for testing, but you can override. See asyn
        method.
        """
        coro = self._aadb.install(apkfile, **kwargs)
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

    def reconnect(self):
        """Reconnect from device side."""
        return get_kernel().run(self._aadb.reconnect())

    async def logcat(self, stdoutstream, stderrstream, longform=False, logtags=""):
        """Coroutine for streaming logcat output to the provided file-like
        streams.
        """
        await self._aadb.logcat(stdoutstream, stderrstream, longform=longform, logtags=logtags)


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

    SYNC_MSG = struct.Struct("<II")
    DIRENT = struct.Struct("<IIIII")  # id; mode; size; time; namelen;

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

    async def send_request(self, protoid: int, path_and_mode: str):
        path_and_mode = path_and_mode.encode("utf-8")
        length = len(path_and_mode)
        if length > 1024:
            raise ValueError("Can't send message > 1024")
        hdr = SyncProtocol.SYNC_MSG.pack(protoid, length)
        await self.socket.sendall(hdr + path_and_mode)

    async def list(self, path, cb_coro):
        await self.send_request(SyncProtocol.ID_LIST, path)
        while True:
            resp = await self.socket.recv(SyncProtocol.DIRENT.size)
            msgid, mode, size, time, namelen = SyncProtocol.DIRENT.unpack(resp)
            if msgid == SyncProtocol.ID_DONE:
                return True
            if msgid != SyncProtocol.ID_DENT:
                return False
            name = await self.socket.recv(namelen)
            stat = os.stat_result((mode, None, None, None, 0, 0, size, None, time, None))
            await cb_coro(stat, name.decode("utf-8"))


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
    import sys
    import signal
    from devtest.io.reactor import SignalEvent
    from devtest import debugger
    debugger.autodebug()
    start_server()
    print("Test AdbClient:")
    c = AdbClient()
    print("  Server version:", c.server_version)
    for devinfo in c.get_device_list():
        print("    ", devinfo)
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
    ac.close()
    del ac

    # Test async with logcat. ^C to stop it.
    async def dostuff():
        ac = await AsyncAndroidDeviceClient(devinfo.serial)

        stdout, stderr, es = await ac.command(["ls", "/sdcard"])
        print("    ", es)
        print("    stdout:", repr(stdout))
        print("    stderr:", repr(stderr))

        signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
        await ac.wait_for("device")
        try:
            task = await spawn(ac.logcat(sys.stdout.buffer, sys.stdout.buffer))
            await signalset.wait()
            await task.cancel()
        finally:
            await ac.close()

    kern = get_kernel()
    kern.run(dostuff)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
