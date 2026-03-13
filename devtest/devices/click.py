"""Controller interface for Click PLC.
"""
from __future__ import annotations

from devtest import logging
from devtest.io import reactor
from devtest.protocols import modbus
from devtest.core import exceptions
from devtest.devices import Controller


class ClickControllerError(exceptions.ControllerError):
    """Raised on errors in an ClickController."""


class ClickController(Controller):
    pass


class RelayController(ClickController):
    """Controller for Click with a relay module."""

    Y001 = 8192  # register offset for relays

    def initialize(self):
        super().initialize()
        self._log = logging.get_logger(self._equipment.name)
        self._client = modbus.ModbusTcpClient(str(self._equipment.primary_interface.ipaddr.ip))

    def close(self):
        if self._client is not None:
            reactor.get_kernel().run(self._client.close())
            self._client = None
            self._log.close()
            self._log = None
        super().close()

    async def _async_write_coil(self, number: int, value: int):
        async with self._client:
            await self._client.write_coil(number, value)

    def _sync_write_coil(self, number: int, value: int):
        return reactor.get_kernel().run(self._async_write_coil(number, value))

    def relay_on(self, number: int):
        """Turn relay on.

        Turn on the PLC relay labeled 'Y<number>' on the device.

        Args:
            number: number of relay, 1 to 6.
        """
        self._log.debug(f"relay_on: {number}")
        return self._sync_write_coil(RelayController.Y001 + number - 1, 1)

    def relay_off(self, number: int):
        """Turn relay off.

        Args:
            number: number of relay, 1 to 6.
        """
        self._log.debug(f"relay_off: {number}")
        return self._sync_write_coil(RelayController.Y001 + number - 1, 0)
