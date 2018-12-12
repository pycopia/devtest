#!/usr/bin/env python3.6

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A service for using Monsoon current and voltage measuring device.
"""

from devtest import logging
from devtest.core import constants
from devtest.core import exceptions
from devtest.os import process
from devtest.devices.monsoon import core as monsoon_core
from . import Service


class MonsoonService(Service):
    """Provide a Monsoon based measurement service.

    Requires either a USB2 or Power connection from the DUT in the model.
    """

    def __init__(self):
        super().__init__()
        self._used = {}

    def _find_hvpm(self, needer):
        # The equipment model should have a device with a connected HVPM,
        # indicated by a connection entry that has the HVPM as the connected
        # device. Return the Device object on the other side of the connection,
        # or None if not found.
        # This only handles Power or USB2 connections.
        passthrough = None
        hvpm = None
        for conn in needer.connections:
            if conn.type == constants.ConnectionType.USB2:
                if "HVPM" in conn.destination.model.name:
                    passthrough = monsoon_core.USBPassthrough.On
                    hvpm = conn.destination
                    break
            elif conn.type == constants.ConnectionType.Power:
                passthrough = monsoon_core.USBPassthrough.Auto
                hvpm = conn.destination
                break
        return hvpm, passthrough  # model object

    def provide_for(self, needer):
        hvpm, passthrough = self._find_hvpm(needer)
        if hvpm is None:
            raise exceptions.ConfigNotFoundError("Device has no connected HVPM")
        if hvpm.serno in self._used:
            raise exceptions.TestImplementationError(
                "HVPM {} is already being used!".format(hvpm.serno))

        ctx = {
                "serialno": hvpm.serno,
                "passthrough": passthrough,
                "voltage": needer.get("voltage", 4.2),
        }
        pm = process.get_manager()
        logging.info("Providing {} for {}".format(hvpm, needer))
        coproc = pm.coprocess()
        coproc.start(domeasure, ctx)
        self._used[hvpm.serno] = coproc

    def release_for(self, needer):
        hvpm, _ = self._find_hvpm(needer)
        result = None
        if hvpm is not None:
            logging.info("Releasing {} for {}".format(hvpm, needer))
            coproc = self._used.pop(hvpm.serno, None)
            if coproc is not None:
                logging.info("Interrupting Monsoon")
                coproc.interrupt()
                result = coproc.wait()
        return result

    def close(self):
        while self._used:
            serno, coproc = self._used.popitem()
            try:
                coproc.interrupt()
                coproc.wait()
            except Exception as ex:
                logging.exception_warning("Leftover monsonn during close, errored", ex)
        self._server = None


# This runs in the coprocess
def domeasure(ctx):
    """Perform a power measurement for an indefinite time.
    """
    # Imports are here because this runs in a subprocess
    import signal
    from devtest.devices.monsoon import measure
    from devtest.devices.monsoon import simple as monsoon_simple

    def _stop(sig, f):
        raise monsoon_simple.StopSampling("stop!")

    dev = monsoon_simple.HVPM()
    dev.open(ctx["serialno"])

    dev.voltage_channel = ctx.get("voltage_channel",
                                  monsoon_core.VoltageChannel.MainAndUSB)
    dev.usb_passthrough = ctx.get("passthrough",
                                  monsoon_core.USBPassthrough.Auto)
    dev.voltage = ctx.get("voltage", 4.2)

    handler = measure.AveragePowerHandler(ctx, dev.info)
    oldint = signal.signal(signal.SIGINT, _stop)
    oldterm = signal.signal(signal.SIGTERM, _stop)
    try:
        captured, dropped = dev.capture(samples=4294967295, handler=handler)
    finally:
        dev.close()
        signal.signal(signal.SIGINT, oldint)
        signal.signal(signal.SIGTERM, oldterm)
    handler.finalize(captured, dropped)
    return handler


def initialize(manager):
    srv = MonsoonService()
    manager.register(srv, "monsoon")


def finalize(manager):
    srv = manager.unregister("monsoon")
    srv.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
