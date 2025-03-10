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
"""Asynchronous core. Unify the asynchronous functions here.
"""

from __future__ import generator_stop

import os
import fcntl
import signal
import atexit

from devtest import logging  # This must be first
from devtest.os import eventloop

# Re-exported curio objects.
from curio import (
    AWAIT,
    Kernel,
    sleep,
    spawn,
    CancelledError,
    TaskError,
    TaskTimeout,
    Queue,  # noqa
    UniversalEvent,
    Event,
    Lock,
    RLock,
    timeout_after,
    TaskGroup,
    run_in_thread)

__all__ = [
    "AWAIT",
    "get_kernel",
    "get_new_kernel",
    "Kernel",
    "sleep",
    "spawn",
    "CancelledError",
    "TaskError",
    "TaskTimeout",
    "Queue",
    "Event",
    "SignalEvent",
    "Lock",
    "RLock",
    "timeout_after",
    "TaskGroup",
    "run_in_thread",
]

_default_kernel = None


class SignalEvent(UniversalEvent):

    def __init__(self, *signos):
        super().__init__()
        self._old = old = {}
        for signo in signos:
            orig = signal.signal(signo, self._handler)
            old[signo] = orig

    def _handler(self, signo, frame):
        self.set()

    def __del__(self):
        while self._old:
            signo, handler = self._old.popitem()
            try:
                signal.signal(signo, handler)
            except TypeError:  # spurious TypeError happens during shutdown.
                pass


def get_kernel(selector=None, with_monitor=False):
    """Return an curio.Kernel object with our selector.

    This is a singleton object.
    """
    global _default_kernel
    if _default_kernel is None:
        _get_kernel(selector=selector)
        if with_monitor or 'CURIOMONITOR' in os.environ:
            from curio.monitor import Monitor
            m = Monitor(_default_kernel)
            _default_kernel._call_at_shutdown(m.close)
    return _default_kernel


def shutdown_kernel():
    _shutdown_kernel()


def _get_kernel(selector=None):
    global _default_kernel
    selector = selector or eventloop.EventLoop()
    _default_kernel = Kernel(selector=selector)
    atexit.register(_shutdown_kernel)


def get_new_kernel(**kwargs):
    selector = eventloop.EventLoop()
    kwargs["selector"] = selector
    return Kernel(**kwargs)


def _shutdown_kernel():
    global _default_kernel
    if _default_kernel is not None:
        kern = _default_kernel
        _default_kernel = None
        logging.info("Shutting down curio.Kernel at exit.")
        kern.run(None, shutdown=True)


def set_asyncio(fd_or_obj):
    """Sets file descriptor or object to raise SIGIO on readiness."""
    if isinstance(fd_or_obj, int):
        fd = fd_or_obj
    else:
        fd = fd_or_obj.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    flags |= os.O_ASYNC
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)
    fcntl.fcntl(fd, fcntl.F_SETOWN, os.getpid())


class SIGIOHandler:

    def __init__(self):
        self.on()

    def on(self):
        signal.signal(signal.SIGIO, self)
        signal.siginterrupt(signal.SIGIO, True)

    def off(self):
        signal.signal(signal.SIGIO, signal.SIG_IGN)

    def __call__(self, sig, frame):
        get_kernel().run(None)


def _test(argv):
    from curio import tcp_server

    kern = get_kernel()
    kern2 = get_kernel()

    assert kern is kern2

    async def _echo_handler(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(100)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')

    k = get_kernel()
    print("Server running. run 'nc localhost 5123' to test it.")
    k.run(tcp_server('', 5123, _echo_handler))


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
