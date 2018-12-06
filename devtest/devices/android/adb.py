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

from devtest import ringbuffer
from devtest.io import socket
from devtest.os import process
from devtest.os import procutils
from devtest.os import exitstatus
from devtest.io.reactor import get_kernel


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
        return AndroidDeviceClient(
            serial, host=self._conn.host, port=self._conn.port)

    def get_device_list(self):
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

    @property
    def server_version(self):
        resp = self._message(b"host:version")
        return int(resp, 16)


class AndroidDeviceClient:
    """An active adb client per device.

    For device specific operations.
    """
    def __init__(self, serial, host="localhost", port=ADB_PORT):
        self.serial = serial.encode("ascii")
        self._conn = AdbConnection(host=host, port=port)
        self.features = self.get_features()

    def close(self):
        if self._conn is not None:
            get_kernel().run(self._conn.close())
            self._conn = None

    def _message(self, msg):
        if self._conn is None:
            raise Error("Operation on a closed device client.")
        return get_kernel().run(_transact(self._conn, msg))

    def get_state(self):
        msg = b"host-serial:%b:get-state" % (self.serial,)
        resp = self._message(msg)
        return resp.decode("ascii")

    def reboot(self):
        get_kernel().run(_connect_command(self.serial, self._conn, b"reboot:"))

    def remount(self):
        resp = get_kernel().run(_special_command(self.serial, self._conn,
                                                 b"remount:"))
        return resp.decode("ascii")

    def root(self):
        resp = get_kernel().run(_special_command(self.serial, self._conn,
                                                 b"root:"))
        return resp.decode("ascii")

    def get_features(self):
        msg = b"host-serial:%b:features" % (self.serial,)
        resp = self._message(msg)
        return resp.decode("ascii")

    def forward(self, hostport, devport):
        """Tell server to start forwarding TCP ports.
        """
        msg = b"host-serial:%b:forward:tcp:%d;tcp:%d" % (self.serial,
                                                         hostport, devport)
        get_kernel().run(_command_transact(self._conn, msg))

    def kill_forward(self, hostport):
        """Tell server to remove forwarding TCP ports.
        """
        msg = b"host-serial:%b:killforward:tcp:%d" % (self.serial, hostport)
        get_kernel().run(_command_transact(self._conn, msg))

    def wait_for(self, state: str):
        """Wait for device to be in a particular state.

        State must be one of {"any", "bootloader", "device", "recovery", "sideload"}
        """
        if state not in {"any", "bootloader", "device", "recovery", "sideload"}:
            raise ValueError("Invalid state to wait for.")
        msg = b"host-serial:%b:wait-for-usb-%b" % (self.serial, state.encode("ascii"))
        get_kernel().run(_command_transact(self._conn, msg))

    def command(self, cmdline, usepty=False):
        """Run a non-interactive shell command.

        Uses ring buffers to collect outputs to avoid a runaway device command
        from filling host memory. However, this might possibly truncate output.

        Returns:
            stdout (string): output of command
            stderr (string): error output of command
            exitstatus (ExitStatus): the exit status of the command.
        """
        if "shell_v2" not in self.features:
            raise AdbCommandFail("Only shell v2 protocol currently supported.")
        if isinstance(cmdline, list):
            name = cmdline[0]
            cmdline = " ".join('"{}"'.format(s) if " " in s else str(s) for s in cmdline)
        else:
            name = cmdline.split()[0]
        cmdline = cmdline.encode("utf8")
        kern = get_kernel()
        kern.run(_start_shell(self.serial, self._conn, usepty, cmdline))
        sp = ShellProtocol(self._conn.socket)
        stdout = ringbuffer.RingBuffer(MAX_PAYLOAD)
        stderr = ringbuffer.RingBuffer(MAX_PAYLOAD)
        resp = kern.run(sp.run(None, stdout, stderr))
        kern.run(self._conn.close())
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


class AndroidDevice:

    def __init__(self, serial, product, model, device):
        self.type = "phone"
        self.serial = serial
        self.product = product
        self.model = model
        self.device = device

    def __repr__(self):
        return ("AndroidDevice("
                "serial={!r}, product={!r}, model={!r}, device={!r})".format(
                    self.serial, self.product, self.model, self.device))


# b'HTxxxserial device usb:1-1.1 product:marlin model:Pixel_XL device:marlin\n'
def _device_factory(line):
    parts = line.decode("ascii").split()
    serial = parts[0]
    product = parts[3].partition(":")[2]
    model = parts[4].partition(":")[2]
    device = parts[5].partition(":")[2]
    return AndroidDevice(serial, product, model, device)


if __name__ == "__main__":
    from devtest import debugger
    debugger.autodebug()
    start_server()
    print("Test AdbClient")
    c = AdbClient()
    print(c.server_version)
    for devinfo in c.get_device_list():
        print(devinfo)
    # c.forward(devinfo.serial, 8080, 8080)
    c.close()
    del c

    print("Test AndroidDeviceClient")
    ac = AndroidDeviceClient(devinfo.serial)
    print("features:", ac.features)
    print(ac.get_state())
    stdout, stderr, es = ac.command(["ls", "/sdcard"])
    print(es)
    print("stdout:", repr(stdout))
    print("stderr:", repr(stderr))
    print(ac.wait_for("device"))
    ac.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
