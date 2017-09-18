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

from devtest.io import socket
from devtest.os import process
from devtest.os import procutils
from devtest.io.reactor import get_kernel

ADB = procutils.which("adb")
if ADB is None:
    raise ImportError("The adb program was not found in PATH. "
                      "This module will not work.")

ADB_PORT = 5037


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

    async def message(self, msg):
        msg = b"%04x%b" % (len(msg), msg)
        await self.socket.sendall(msg)
        stat = await self.socket.recv(4)
        if stat == b"OKAY":
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
            raise AdbCommandFail(resp.decode("ascii"))
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
async def _forward_transact(conn, msg):
    await conn.open()
    msg = b"%04x%b" % (len(msg), msg)
    await conn.socket.sendall(msg)
    connstat = await conn.socket.recv(4)
    if connstat == b"OKAY":
        stat = await conn.socket.recv(4)
        if stat != b"OKAY":
            raise AdbCommandFail("forward status not OKAY")
    elif stat == b"FAIL":
        lenst = await conn.socket.recv(4)
        length = int(lenst, 16)
        resp = await conn.socket.recv(length)
        await conn.close()
        raise AdbCommandFail(resp.decode("ascii"))
    else:
        await conn.close()
        raise AdbProtocolError(stat.decode("ascii"))


async def _shell_transact(serial, conn, cmdline):
    msg = b"host:transport:%b" % serial
    await conn.open()
# TODO


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
        get_kernel().run(_forward_transact(self._conn, msg))

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

    def close(self):
        if self._conn is not None:
            get_kernel().run(self._conn.close())
            self._conn = None

    def _message(self, msg):
        if self._conn is None:
            raise Error("Operation on a closed device client.")
        return get_kernel().run(_transact(self._conn, msg))

    @property
    def state(self):
        msg = b"host-serial:%b:get-state" % (self.serial,)
        resp = self._message(msg)
        return resp.decode("ascii")

    def forward(self, hostport, devport):
        """Tell server to start forwarding TCP ports.
        """
        msg = b"host-serial:%b:forward:tcp:%d;tcp:%d" % (self.serial,
                                                         hostport, devport)
        get_kernel().run(_forward_transact(self._conn, msg))

    def shell(self, cmdline):
        get_kernel().run(_shell_transact(self.serial, self._conn, cmdline))


class AndroidDevice:

    def __init__(self, serial, product, model, device):
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
    c = AdbClient()
    print(c.server_version)
    for devinfo in c.get_device_list():
        print(devinfo)
    c.forward(devinfo.serial, 8080, 8080)
    c.close()

    ac = AndroidDeviceClient(devinfo.serial)
    print(ac.state)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
