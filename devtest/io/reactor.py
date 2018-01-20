#!/usr/bin/env python3.5

"""
Asynchronous core. Unify the asynchronous functions here.
"""

from __future__ import generator_stop

import atexit

from devtest import logging  # This must be first
from devtest.os import eventloop

from curio import (Kernel, sleep, spawn, CancelledError, TaskError, TaskTimeout, # noqa
                   Event, timeout_after)


_default_kernel = None


def get_kernel(selector=None):
    """Return an curio.Kernel object with our selector.

    This is a singleton object.
    """
    global _default_kernel
    if _default_kernel is None:
        _get_kernel(selector=selector)
    if _default_kernel._crashed:
        logging.warning("Reactor kernel crashed. Attempting shutdown and build new one.")
        _default_kernel.run(shutdown=True)
        _default_kernel = None
        _get_kernel(selector=selector)
    return _default_kernel


def _get_kernel(selector=None):
    global _default_kernel
    selector = selector or eventloop.EventLoop()
    _default_kernel = Kernel(selector=selector)
    atexit.register(_shutdown_kernel)


def get_new_kernel(selector=None):
    selector = selector or eventloop.EventLoop()
    return Kernel(selector=selector)


def _shutdown_kernel():
    global _default_kernel
    if _default_kernel is not None:
        kern = _default_kernel
        _default_kernel = None
        logging.info("Shutting down curio.Kernel at exit.")
        kern.run(None, shutdown=True)


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
