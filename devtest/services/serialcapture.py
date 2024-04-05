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
Serial logging service. Logs any number of serial ports to files.

Runs a server as a single subthread. The subthread runs an asychronous event
loop managing all of the added ports.

The equipment needs an attribute named "console", e.g.:

    console={"device": "/dev/ttyS0", "setup": "115200 8N1"}

May be set using the devtestadmin tool:

    devtestadmin eq  <devname> attrib set console '{"device": "/dev/ttyS0", "setup": "115200 8N1"}'

"""  # noqa

from __future__ import generator_stop

import os
import threading
import struct
import pickle
import time

from devtest import logging
from devtest.qa import signals
from devtest.core import exceptions
from devtest.io import socket
from devtest.io import serial
from devtest.io.reactor import get_kernel, get_new_kernel, spawn, Event
from devtest.io.streams import FileStream

from . import Service

CONTROL_SOCKET = "/var/tmp/devtest_serialcapture_control.sock"

# Command tags
STOP = 1
SET_LOGDIR = 2
ADD_CHANNEL = 3
CLOSE_CHANNEL = 4

# Response tags
OK = 100
ERROR = 500
STOPPED = 101

PACKER = struct.Struct("!II")


class SerialCaptureService(Service):

    def __init__(self):
        self._server = None
        signals.logdir_location.connect(self._set_logdir, weak=False)
        self._set_logdir(None, path="/var/tmp")

    def _set_logdir(self, runner, path=None):
        self._logdir = path
        self.set_logdir(path)

    def _start_server(self):
        if self._server is None:
            self._server = SerialCaptureServer()
            self._server.start()
            time.sleep(1)
            self.set_logdir(self._logdir)

    def provide_for(self, device, **kwargs):
        self._start_server()
        hostname = device.get("hostname")
        console_config = device.get("console")
        if console_config:
            devicenode = console_config.get("device")
            if devicenode:
                setup = console_config.get("setup", "115200 8N1")
                self.add_channel(hostname, devicenode, setup)
            else:
                logging.warning("SerialCaptureService no serial device for {}.".format(hostname))
        else:
            logging.warning("SerialCaptureService no console config for {}.".format(hostname))

    def release_for(self, device, **kwargs):
        hostname = device.get("hostname")
        console_config = device.get("console")
        if console_config:
            devicenode = console_config.get("device")
            if devicenode:
                self.close_channel(hostname, devicenode)
            else:
                logging.warning("SerialCaptureService no serial device for {}.".format(hostname))
        else:
            logging.warning("SerialCaptureService no console config for {}.".format(hostname))

    def close(self):
        if self._server is not None:
            signals.logdir_location.disconnect(self._set_logdir)
            srv = self._server
            self._server = None
            _send_message(STOP, None)
            srv.join(timeout=2.0)
            if srv.is_alive():
                raise RuntimeError("SerialCaptureService server thread did not terminate.")

    def set_logdir(self, path):
        """Set the directory where log files will be created."""
        if self._server is not None:
            return _send_message(SET_LOGDIR, path)

    def add_channel(self, name, devicenode, setup):
        """Add a serial capture channel.

        Parameters:
            name: arbitrary name
            devicenode: name of tty device (e.g. /dev/cu.xxx)
            setup: serial port setup string (e.g. "115200 8N1")
        """
        resp, msg = _send_message(ADD_CHANNEL, {
            "name": name,
            "devicenode": devicenode,
            "setup": setup
        })
        if resp != OK:
            raise exceptions.ConfigError(msg)

    def close_channel(self, name, devicenode):
        """Close a previously added channel, indexed by name, devicenode pair.

        Parameters:
            name: arbitrary name
            devicenode: name of tty device (e.g. /dev/cu.xxx)
        """
        resp, msg = _send_message(CLOSE_CHANNEL, {"name": name, "devicenode": devicenode})
        if resp != OK:
            raise exceptions.ConfigError(msg)


def _send_message(tag, data):
    kern = get_kernel()
    return kern.run(_send_message_coro(tag, data))


async def _send_message_coro(tag, data):
    try:
        msg = _protocol_encode(tag, data)
        sock = await socket.open_unix_connection(CONTROL_SOCKET)
        await sock.sendall(msg)
    except Exception as ex:
        logging.exception_error("_send_message_coro send: {}".format(tag), ex)
        return ERROR, str(ex)
    try:
        head = await sock.recv(PACKER.size, socket.MSG_WAITALL)
        rtag, pl = PACKER.unpack(head)
        p = await sock.recv(pl, socket.MSG_WAITALL)
        await sock.close()
        rdata = pickle.loads(p)
    except Exception as ex:
        logging.exception_error("_send_message_coro receive", ex)
        return ERROR, str(ex)
    return rtag, rdata


class SerialCaptureServer(threading.Thread):
    """Server thread that runs an async event loop managing a collection of serial ports.
    """

    def run(self):
        self._data = threading.local()
        try:
            os.unlink(CONTROL_SOCKET)
        except OSError:
            pass
        self._data.logdir = "/var/tmp"
        self._data.channels = {}
        logging.info("SerialCaptureServer starting.")
        kern = get_new_kernel()
        kern.run(self._unix_server(), shutdown=True)
        logging.info("SerialCaptureServer ended.")

    async def _unix_server(self):
        self._server_stop = Event()
        cserver = await spawn(socket.unix_server(CONTROL_SOCKET, self._handler))
        await self._server_stop.wait()
        await cserver.cancel()

    async def _handler(self, client, addr):
        head = await client.recv(PACKER.size, socket.MSG_WAITALL)
        tag, pl = PACKER.unpack(head)
        p = await client.recv(pl, socket.MSG_WAITALL)
        data = pickle.loads(p)
        try:
            resptag, respval = await self._dispatch(tag, data)
        except Exception as ex:
            logging.exception_error("_handler", ex)
            await client.sendall(_protocol_encode(ERROR, str(ex)))
        else:
            await client.sendall(_protocol_encode(resptag, respval))
        if resptag == STOPPED:
            await self._server_stop.set()

    async def _dispatch(self, tag, data):
        if tag == STOP:
            while self._data.channels:
                (name, devicenode), (chan, copy_task) = self._data.channels.popitem()
                logging.info("SerialCaptureServer stopping {}".format(chan))
                await copy_task.cancel()
                await chan.close()
            logging.info("SerialCaptureServer STOPPED")
            return STOPPED, "Server stopped"
        elif tag == SET_LOGDIR:
            self._data.logdir = data
            logging.info("SerialCaptureServer set logdir: {}".format(self._data.logdir))
            return OK, self._data.logdir
        elif tag == ADD_CHANNEL:
            job = data
            if self._data.channels.get((job["name"], job["devicenode"])) is not None:
                return OK, "Channel already added."
            job["logdir"] = self._data.logdir
            try:
                sc = SerialChannel(job)
                copy_task = await spawn(sc.copy())
                self._data.channels[(job["name"], job["devicenode"])] = (sc, copy_task)
                logging.info("SerialCaptureServer ADD_CHANNEL {}".format(sc))
                return OK, str(sc)
            except Exception as ex:
                return ERROR, str(ex)
        elif tag == CLOSE_CHANNEL:
            job = data
            sc, copy_task = self._data.channels.pop((job["name"], job["devicenode"]), (None, None))
            if sc:
                try:
                    logging.info("SerialCaptureServer CLOSE_CHANNEL {}".format(sc))
                    await copy_task.cancel()
                    await sc.close()
                except Exception as ex:
                    return ERROR, str(ex)
                return OK, "channel closed"
            else:
                return OK, "Channel was not open"
        else:
            logging.error("SerialCaptureServer unkown tag: {}".format(tag))
            return ERROR, "Unknown tag"


class SerialChannel:

    def __init__(self, job):
        basename = job.get("filename", "console_{}.log".format(job["name"]))
        fname = os.path.join(job["logdir"], basename)
        self._outf = FileStream(open(fname, "ab"))
        ser = serial.SerialPort(fname=job["devicenode"], mode="rb", setup=job["setup"])
        self._ser = FileStream(ser)

    def __str__(self):
        if self._outf is not None:
            return "SerialChannel: {} -> {}".format(self._ser._file.name, self._outf._file.name)
        else:
            return "SerialChannel: closed"

    async def copy(self):
        while 1:
            data = await self._ser.read(4096)
            await self._outf.write(data)
            await self._outf.flush()

    async def close(self):
        if self._outf is not None:
            await self._outf.close()
            await self._ser.close()
            self._outf = None
            self._ser = None


def _protocol_encode(tag, value):
    data = pickle.dumps(value)
    head = PACKER.pack(tag, len(data))
    return head + data


def initialize(manager):
    srv = SerialCaptureService()
    manager.register(srv, "seriallog")


def finalize(manager):
    srv = manager.unregister("seriallog")
    srv.close()


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
