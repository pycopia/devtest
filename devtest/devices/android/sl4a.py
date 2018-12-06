#!/usr/bin/env python3.6
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""An interface to SL4A on an Android device.

Supports original and a new protocol.

NOTE: New protocol is not implemented yet.
"""

import struct
import json

import portpicker

from devtest.io import reactor
from devtest.io import socket

_get_kernel = reactor.get_kernel

__all__ = ['SL4AProtocolError', 'SL4AInterface']

DEVICE_PORT = 8081


class Error(Exception):
    pass


class SL4AProtocolError(Error):
    pass


class Encoder(json.JSONEncoder):
    def __init__(self):
        super(Encoder, self).__init__(ensure_ascii=False)


class Decoder(json.JSONDecoder):
    pass


_json_decoder = Decoder()
_json_encoder = Encoder()


def loadb(data):
    """Decode a bytes object into Python objects."""
    return _json_decoder.decode(data.decode("utf-8"))


def dumpb(obj):
    """Encode a Python object into bytes."""
    return _json_encoder.encode(obj).encode("utf-8")


def counter():
    """Generic counter generator."""
    i = 0
    while 1:
        yield i
        i += 1


class _OldSL4AProtocol:
    """Implementation of existing (old) SL4A RPC protocol.
    """
    UNKNOWN_UID = -1

    def __init__(self, sock):
        self._stream = sock.as_stream()
        self._counter = counter()
        self._uid = -1

    @property
    def sessionid(self):
        return self._uid

    async def connect(self, sessionid=-1):
        self._uid = sessionid
        if self._uid == _OldSL4AProtocol.UNKNOWN_UID:
            await self._initiate()
        else:
            await self._continue()

    async def close(self):
        rpcid = next(self._counter)
        data = {'id': rpcid, 'method': 'closeSl4aSession', 'params': ()}
        await self._send(data)
        await self._stream.close()
        self._uid = _OldSL4AProtocol.UNKNOWN_UID
        self._counter = None

    def rpc(self, methodname, args, kwargs):
        resp = _get_kernel().run(self._rpc, methodname, args, kwargs)
        return resp

    async def _initiate(self):
        data = {"cmd": "initiate", "uid": self._uid}
        result = await self._transact(data)
        if result['status']:  # This will never be False, but...
            self._uid = result['uid']
        else:
            raise SL4AProtocolError("Did not initialize connection:" + result)

    async def _continue(self):
        data = {"cmd": "continue", "id": self._uid}
        result = await self._transact(data)
        if result['status']:  # This will never be False, but...
            self._uid = result['uid']
        else:
            raise SL4AProtocolError("Did not initialize connection:" + result)

    async def _transact(self, data):
        await self._send(data)
        resp = await self._receive()
        return resp

    async def _send(self, data):
        return await self._stream.write(dumpb(data) + b'\n')

    async def _receive(self):
        resp = await self._stream.readline()
        return loadb(resp)

    async def _rpc(self, methodname, args, kwargs):
        rpcid = next(self._counter)
        data = {'id': rpcid, 'method': methodname, 'params': args}
        resp = await self._transact(data)
        if resp["id"] != rpcid:
            raise SL4AProtocolError("RPC response id did not match request.")
        if resp["error"] is not None:
            raise SL4AProtocolError(resp["error"])
        return resp["result"]


class _SL4AProtocol:
    """Implementation of new SL4A protocol.

    This is a multiplexed TLV style protocol.

    TODO
    """

    def __init__(self, sock):
        self._packer = struct.Struct("!LQ")  # tag, length
        self._sock = sock
        self._uid = -1

    async def connect(self, sessionid=-1):
        pass

    async def close(self):
        pass

    def rpc(self, methodname, args, kwargs):
        resp = _get_kernel().run(self._rpc, methodname, args, kwargs)
        return resp

    async def _rpc(self, methodname, args, kwargs):
        return NotImplemented



class SL4AInterface:
    """Interface to SL4A server running on device."""

    START = ('am start -a com.googlecode.android_scripting.action.LAUNCH_SERVER '
             '--ei com.googlecode.android_scripting.extra.USE_SERVICE_PORT {device_port} '
             'com.googlecode.android_scripting/.activity.ScriptingLayerServiceLauncher')

    STOP = ('am start -a com.googlecode.android_scripting.action.KILL_PROCESS '
            '--ei com.googlecode.android_scripting.extra.PROXY_PORT {device_port} '
            'com.googlecode.android_scripting/.activity.ScriptingLayerServiceLauncher')

    def __init__(self, adb, device_port=DEVICE_PORT):
        self._adb = adb
        self.host_port = None
        self.device_port = device_port

    def close(self):
        if self.host_port is not None:
            _get_kernel().run(self._close)
            cmd = SL4AInterface.STOP.format(device_port=self.device_port)
            self._adb.command(cmd.split())
            self._adb.kill_forward(self.host_port)
            self.host_port = None
            self._proto = None
            self._adb = None

    async def _close(self):
        await self._proto.close()

    def connect(self, newprotocol=False, sessionid=-1):
        if self.host_port is None:
            host_port = portpicker.pick_unused_port()
            self.host_port = host_port
            self._adb.forward(host_port, self.device_port)
        cmd = SL4AInterface.START.format(device_port=self.device_port)
        self._adb.command(cmd.split())
        _get_kernel().run(self._connect, newprotocol, sessionid)

    async def _connect(self, newprotocol, sessionid):
        sock = socket.socket(socket.AF_INET,
                             socket.SOCK_STREAM,
                             socket.IPPROTO_TCP)
        await reactor.sleep(3)  # Time for sl4a server to initialize
        await sock.connect(("localhost", self.host_port))
        if newprotocol:
            self._proto = _SL4AProtocol(sock)
        else:
            self._proto = _OldSL4AProtocol(sock)
        await self._proto.connect(sessionid)

    def __getattr__(self, name):
        def _fun(*args, **kwargs):
            return self._proto.rpc(name, args, kwargs)
        return _fun

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
