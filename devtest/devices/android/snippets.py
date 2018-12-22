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

"""An interface to snippets on an Android device.

Implemented as asynchronous coroutines.
"""

import portpicker

from devtest import json
from devtest import ringbuffer
from devtest.io import socket
from devtest.io import reactor


_get_kernel = reactor.get_kernel


class Error(Exception):
    pass


class SnippetsProtocolError(Error):
    pass


class SnippetsError(Error):
    pass


def counter():
    """Generic counter generator."""
    i = 0
    while 1:
        yield i
        i += 1


class _SnippetsProtocol:
    def __init__(self, adb, serial, package):
        self._adb = adb
        self._serial = serial
        self._package = package
        self.host_port = None
        self._init()


class _OldSnippetsProtocol(_SnippetsProtocol):

    UNKNOWN_UID = -1

    def _init(self):
        self._server_task = None
        host_port = portpicker.pick_unused_port()
        self.host_port = host_port
        self._sock = socket.socket(socket.AF_INET,
                                   socket.SOCK_STREAM,
                                   socket.IPPROTO_TCP)
        self._uid = _OldSnippetsProtocol.UNKNOWN_UID
        self._counter = counter()

    async def close(self):
        if self._sock is None or self._server_task is None:
            return
        await self._rpc_close()
        await self._sock.close()
        argv = ['am', 'instrument', '-w', '-e', 'action', 'stop',
                '{package}/com.google.android.mobly.snippet.SnippetRunner'.format(package=self._package)]
        await self._adb.command(argv)
        await self._server_task.cancel()
        await self._server_task.join()

        # remove host to device forward
        await self._adb.kill_forward(self.host_port)
        self._sock = None
        self._server_task = None

    async def connect(self):
        argv = ['am', 'instrument', '-w', '-e', 'action', 'start',
                '{package}/com.google.android.mobly.snippet.SnippetRunner'.format(package=self._package)]
        stdout = ringbuffer.RingBuffer(4096)
        stderr = ringbuffer.RingBuffer(4096)
        task = await self._adb.start(argv, stdout, stderr)
        await reactor.sleep(3)
        # line1 = b'SNIPPET START, PROTOCOL 1 0\n'
        # line2 = b'SNIPPET SERVING, PORT 42822\n'
        # 🤢
        device_port = None
        for line in stdout.read().splitlines():
            if line.startswith(b"SNIPPET START"):
                pass
            elif line.startswith(b"SNIPPET SERVING"):
                device_port = int(line.split()[-1])
                break
        self._server_task = task
        # Forward host to device port
        if not device_port:
            raise SnippetsProtocolError("Did not get device port!")
        await self._adb.forward(self.host_port, device_port)
        await reactor.sleep(1)
        await self._sock.connect(("localhost", self.host_port))

    def __getattr__(self, name):
        def _fun(*args, **kwargs):
            return self._rpc(name, args, kwargs)
        return _fun

    def _rpc(self, name, args, kwargs):
        return _get_kernel().run(self._arpc(name, args, kwargs))

    async def _rpc_close(self):
        await self._arpc("closeSl4aSession", (), {})
        self._uid = _OldSnippetsProtocol.UNKNOWN_UID
        self._counter = None

    async def _proto_init(self):
        self._uid = _OldSnippetsProtocol.UNKNOWN_UID
        data = {"cmd": "initiate", "uid": self._uid}
        result = await self._transact(data)
        if result['status']:  # This will never be False, but...
            self._uid = result['uid']
        else:
            raise SnippetsProtocolError("Did not initialize connection:" + result)

    async def _transact(self, data):
        await self._send(data)
        return await self._receive()

    async def _send(self, data):
        return await self._sock.sendall(json.encode_bytes(data) + b'\n')

    async def _receive(self):
        resp = await self._sock.as_stream().readline()
        if resp:
            return json.decode_bytes(resp)
        else:
            return None

    async def _arpc(self, methodname, args, kwargs):
        if self._uid == _OldSnippetsProtocol.UNKNOWN_UID:
            await self._proto_init()
        rpcid = next(self._counter)
        data = {'cmd': 'continue', 'uid':self._uid, 'id': rpcid, 'method': methodname, 'params': args}
        resp = await self._transact(data)
        if resp is not None:
            if resp["id"] != rpcid:
                raise SnippetsProtocolError("RPC response id did not match request.")
            if resp["error"] is not None:
                raise SnippetsError(resp["error"])
            return resp["result"]
        else:
            return None


class _NewSnippetsProtocol(_SnippetsProtocol):

    def _init(self):
        pass
#  TODO(dart)


class SnippetsInterface:

    def __init__(self, adb, serial):
        self._adb = adb
        self._serial = serial
        self._protos = {}

    def __getattr__(self, name):
        obj = self._protos.get(name)
        if obj is None:
            raise AttributeError("Not attribute or snippet {!r} found.".format(name))
        return obj

    def close(self):
        _get_kernel().run(self._close)
        self._adb = None

    async def _close(self):
        async with reactor.TaskGroup() as tg:
            while self._protos:
                name, proto = self._protos.popitem()
                await tg.spawn(proto.close)
            await tg.join()

    def load(self, name, package, newprotocol=False):
        """" Starts the snippet apk with the given package name and connects.
        """
        if name not in self._protos:
            if newprotocol:
                self._protos[name] = proto = _NewSnippetsProtocol(self._adb, self._serial, package)
            else:
                self._protos[name] = proto = _OldSnippetsProtocol(self._adb, self._serial, package)
            _get_kernel().run(proto.connect)


if __name__ == "__main__":
    import os
    import time
    import autodebug

    snippets = SnippetsInterface(os.environ["ANDROID_SERIAL"])
    print("loading")
    snippets.load("mbs","com.google.android.mobly.snippet.bundled")
    print("waiting")
    time.sleep(5)
    print(snippets.mbs.getTelephonyCallState())
    print(snippets.mbs.getLine1Number())
    print("closing")
    snippets.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
