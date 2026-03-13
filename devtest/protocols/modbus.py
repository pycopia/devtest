"""Asynchronous Modbus interface.
"""

from __future__ import annotations

from devtest import logging
from devtest.io import socket

from pymodbus.factory import ClientDecoder
from pymodbus.transaction import ModbusSocketFramer, DictTransactionManager
from pymodbus.client.common import ModbusClientMixin


class ModbusTcpClient(ModbusClientMixin):
    """Modbus TCP client.

    The following methods may be used, they form a request and return the `execute` awaitable. ::

        mask_write_register(*args, **kwargs)
        read_coils(address, count=1, **kwargs)
        read_discrete_inputs(address, count=1, **kwargs)
        read_holding_registers(address, count=1, **kwargs)
        read_input_registers(address, count=1, **kwargs)
        readwrite_registers(*args, **kwargs)
        write_coil(address, value, **kwargs)
        write_coils(address, values, **kwargs)
        write_register(address, value, **kwargs)
        write_registers(address, values, **kwargs)

    Args:
        host: host name or IP address of the ModbusTCP device.
        port: The TCP port number, defaults to 502.
    """

    def __init__(self, host, port=502, **kwargs):
        self.framer = ModbusSocketFramer(ClientDecoder())
        self.transaction = DictTransactionManager(self, **kwargs)
        self._host = host
        self._port = int(port)
        self._sock = None
        self._logger = logging.get_logger(self.__class__.__name__)

    def __repr__(self):
        cl = self.__class__
        return f"{cl.__name__}({self._host}, {self._port})"

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

    async def connect(self):
        """Create the TCP connection.
        """
        sock = await socket.create_connection((self._host, self._port))
        self._sock = sock

    async def close(self):
        if self._sock is not None:
            await self._sock.close()
            self._sock = None
        self._logger.close()

    # this is called and returned by base class methods.
    # It performs the actual network transaction when you await on it.
    async def execute(self, request, **kwargs):
        self._resp = None
        # Build and send request
        request.transaction_id = tid = self.transaction.getNextTID()
        packet = self.framer.buildPacket(request)
        await self._sock.sendall(packet)
        self.transaction.addTransaction(request, tid)
        # Receive and check response
        rawresp = await self._sock.recv(1024)
        unit = self.framer.decode_data(rawresp).get("uid", 0)
        self.framer.processIncomingPacket(rawresp, self._response_handler, unit=unit)
        if self._resp is not None:
            resp = self._resp
            self._resp = None
            return resp
        else:
            return None

    def _response_handler(self, reply, **kwargs):
        request = self.transaction.getTransaction(reply.transaction_id)
        if request:
            self._resp = reply
        else:
            self._logger.warning(f"modbus: unrequested message response: {reply}")


# Coroutines for common single-use operations.


async def write_coils(address, offset, values):
    async with ModbusTcpClient(address) as client:
        resp = await client.write_coils(offset, values)
    return resp


async def mask_write_register(address, *args, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.mask_write_register(*args, *kwargs)
    return resp


async def read_coils(address, offset, count=1, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.read_coils(offset, count=1, **kwargs)
    return resp


async def read_discrete_inputs(address, offset, count=1, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.read_discrete_inputs(offset, count=1, **kwargs)
    return resp


async def read_holding_registers(address, offset, count=1, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.read_holding_registers(offset, count=1, **kwargs)
    return resp


async def read_input_registers(address, offset, count=1, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.read_input_registers(offset, count=1, **kwargs)
    return resp


async def readwrite_registers(address, *args, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.readwrite_registers(*args, **kwargs)
    return resp


async def write_coil(address, offset, value, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.write_coil(offset, value, **kwargs)
    return resp


async def write_register(address, offset, value, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.write_register(offset, value, **kwargs)
    return resp


async def write_registers(address, offset, values, **kwargs):
    async with ModbusTcpClient(address) as client:
        resp = await client.write_registers(offset, values, **kwargs)
    return resp
