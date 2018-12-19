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

"""Dynamixel interfaces experiments.
"""

import struct
import enum
import math

from devtest.io import serial


class DynamixelErrorType(enum.IntEnum):
    Instruction = 0x40
    Overload = 0x20
    Checksum = 0x10
    Range = 0x08
    Overheating = 0x04
    AngleLimit = 0x02
    InputVoltage = 0x01


class DynamixelError(Exception):
    pass


class DynamixelChecksumError(DynamixelError):
    pass


class UnsupportedModelError(DynamixelError):
    pass


class DynamixelStatusError(DynamixelError):

    def __str__(self):
        flags = self.args[0]
        if flags:
            return "{}: {}".format(self.__class__.__name__, self._decode_error(flags))
        else:
            # This should never be instantiated if error flags was zero.
            return "{}: No error (fix your code).".format(self.__class__.__name__)

    def _decode_error(self, flags):
        errorlist = []
        for et in DynamixelErrorType:
            if flags & et.value:
                errorlist.append(et.name)
        return " | ".join(errorlist)


class Instruction(enum.IntEnum):
    # Instruction that checks whether the Packet has arrived to a device with
    # the same ID as Packet ID.
    Ping = 0x01
    # Instruction to read data from the Device
    Read = 0x02
    # Instruction to write data on the Device
    Write = 0x03
    # Instruction that registers the Instruction Packet to a standby status;
    # Packet is later executed through the Action instruction
    RegWrite = 0x04
    # Instruction that executes the Packet that was registered beforehand using
    # Reg Write
    Action = 0x05
    # Instruction that resets the Control Table to its initial factory default
    # settings
    FactoryReset = 0x06
    # Instruction that reboots Dynamixel (See applied products in the
    # description) 2.0 only
    Reboot = 0x08
    # Instruction to reset certain information
    Clear = 0x10
    # Return message  2.0 only
    Status = 0x55
    # For multiple devices, Instruction to read data from the same Address with
    # the same length at once. 2.0 only
    SyncRead = 0x82
    # For multiple devices, Instruction to write data on the same Address with
    # the same length at once.
    SyncWrite = 0x83
    # For multiple devices, Instruction to write data on different Addresses
    # with different lengths at once This command can only be used with MX
    # series.
    BulkRead = 0x92
    # For multiple devices, Instruction to write data on different Addresses
    # with different lengths at once. 2.0 only
    BulkWrite = 0x93


class Protocol:

    def __init__(self, device):
        self._dev = device


class Protocol1(Protocol):

    def encode(self, motorid, instruction, data):
        a = bytearray(b"\xFF\xFF\x00\x00")
        a[2] = motorid
        a.append(instruction)
        a.extend(data)
        a[3] = (len(a) - 3) & 0xFF
        ck = (sum(a[2:]) & 0xFF) ^ 0xFF
        a.append(ck)
        return bytes(a)

    def send_message(self, motorid, instruction, data):
        msg = self.encode(motorid, instruction, data)
        self._dev.write(msg)

    def read_response(self):
        resp = self._dev.read(4)
        h1, h2, mid, length = struct.unpack("BBBB", resp)
        assert h1 == 0xFF and h2 == 0xFF
        rest = self._dev.read(length)
        ck = (mid + length + sum(rest[:-1]) & 0xFF) ^ 0xFF
        if ck != rest[-1]:
            raise DynamixelChecksumError("Incorrect checksum")
        error = rest[0]
        if error:
            raise DynamixelStatusError(error)
        return rest[1:-1]


class Protocol2(Protocol):
    pass  # TODO


class Dynamixel:
    """Establishes base type for all Dynamixel."""


class DynamixelAX18A(Dynamixel):
    """A Dynamixel model AX-18A."""

    EEPROM = struct.Struct("<HBBBBHHBBBBHBBB")
    RAM = struct.Struct("<6B6H6BH")  # offset 24
    # EEPROM:
    # 0    2    Model Number    Model Number    R    18
    # 2    1    Firmware Version    Firmware Version    R    -
    # 3    1    ID    DYNAMIXEL ID    RW    1
    # 4    1    Baud Rate    Communication Speed    RW    1
    # 5    1    Return Delay Time    Response Delay Time    RW    250
    # 6    2    CW Angle Limit    Clockwise Angle Limit    RW    0
    # 8    2    CCW Angle Limit    Counter-Clockwise Angle Limit    RW    1023
    # 10   1    unused
    # 11    1    Temperature Limit    Maximum Internal Temperature Limit    RW    75
    # 12    1    Min Voltage Limit    Minimum Input Voltage Limit    RW    60
    # 13    1    Max Voltage Limit    Maximum Input Voltage Limit    RW    140
    # 14    2    Max Torque    Maximun Torque    RW    983
    # 16    1    Status Return Level    Select Types of Status Return    RW    2
    # 17    1    Alarm LED    LED for Alarm    RW    36
    # 18    1    Shutdown    Shutdown Error Information    RW    36
    # RAM:
    # 24    1    Torque Enable    Motor Torque On/Off    RW    0
    # 25    1    LED    Status LED On/Off    RW    0
    # 26    1    CW Compliance Margin    CW Compliance Margin    RW    1
    # 27    1    CCW Compliance Margin    CCW Compliance Margin    RW    1
    # 28    1    CW Compliance Slope    CW Compliance Slope    RW    32
    # 29    1    CCW Compliance Slope    CCW Compliance Slope    RW    32
    # 30    2    Goal Position    Target Position    RW    -
    # 32    2    Moving Speed    Moving Speed    RW    -
    # 34    2    Torque Limit    Torque Limit(Goal Torque)    RW    ADD 14&15
    # 36    2    Present Position    Present Position    R    -
    # 38    2    Present Speed    Present Speed    R    -
    # 40    2    Present Load    Present Load    R    -
    # 42    1    Present Voltage    Present Voltage    R    -
    # 43    1    Present Temperature    Present Temperature    R    -
    # 44    1    Registered    If Instruction is registered    R    0
    # 45    1    unused
    # 46    1    Moving    Movement Status    R    0
    # 47    1    Lock    Locking EEPROM    RW    0
    # 48    2    Punch    Minimum Current Threshold    RW    32

    def __init__(self, serialdevice, motorid):
        self._protocol = Protocol1(serialdevice)
        self.motorid = motorid
        self.read_eeprom()

    def __del__(self):
        self.close()

    @property
    def model(self):
        if self._model is None:
            self._model, self._version = struct.unpack("<HB", self.read_value(0, 3))
        return self._model

    @property
    def version(self):
        if self._version is None:
            self._model, self._version = struct.unpack("<HB", self.read_value(0, 3))
        return self._version

    def close(self):
        if self._protocol is not None:
            self._protocol = None

    def ping(self):
        self._protocol.send_message(self.motorid, Instruction.Ping, b'')
        self._protocol.read_response()
        return True

    def read_value(self, address, length):
        self._protocol.send_message(self.motorid, Instruction.Read,
                                    bytes([address, length]))
        return self._protocol.read_response()

    def write_value(self, address, value, length):
        fmt = {1: "BB", 2: "<BH", 4: "<BI"}[length]
        bval = struct.pack(fmt, address, value)
        self._protocol.send_message(self.motorid, Instruction.Write, bval)
        if self._status_return_level == StatusReturnLevel.All:
            self._protocol.read_response()

    def write_values(self, address, *values):
        self._protocol.send_message(self.motorid, Instruction.Write,
                                    bytes((address,) + values))

    def registered_write_values(self, address, *values):
        self._protocol.send_message(self.motorid, Instruction.RegWrite,
                                    bytes((address,) + values))
        self._protocol.read_response()

    def action(self):
        self._protocol.send_message(0xFE, Instruction.Action, b"")

    def read_eeprom(self):
        raw = self.read_value(0, DynamixelAX18A.EEPROM.size)
        if len(raw) != DynamixelAX18A.EEPROM.size:
            return
        resp = DynamixelAX18A.EEPROM.unpack(self.read_value(0, DynamixelAX18A.EEPROM.size))
        (self._model, self._version, self.motorid, baud, rtd, angle_limit_cw,
         angle_limit_ccw, _, temp_limit, min_v_limit, max_v_limit, max_torque,
         status_return, alarm_led, shutdown_info) = resp
        self._baudcode = baud
        self._return_delay_time = 2 * rtd  # usec
        self._angle_limit_cw = float(math.ceil(angle_limit_cw / 3.4133332284757363))
        self._angle_limit_ccw = float(math.ceil(angle_limit_ccw / 3.4133332284757363))
        self._min_voltage_limit = min_v_limit / 10.
        self._max_voltage_limit = max_v_limit / 10.
        self._max_torque = float(math.ceil(max_torque / 10.23))
        self._status_return_level = StatusReturnLevel(status_return)

    def read_ram(self):
        raw = self.read_value(24, DynamixelAX18A.RAM.size)
        resp = DynamixelAX18A.RAM.unpack(raw)
        print("XXX ram:", repr(resp))

#    def factory_reset(self):
#        self._protocol.send_message(self.motorid, Instruction.FactoryReset, b"")
#        print("factory reset:", self._protocol.read_response())

    @property
    def baud(self):
        return _BAUD_CODES[self._baudcode]

    @baud.setter
    def baud(self, baud):
        new = _BAUD_CODES_REV[baud]
        self.write_value(4, new, 1)
        self._baudcode = new

    @property
    def return_delay_time(self):
        """Return delay time (uS)."""
        return self._return_delay_time

    @return_delay_time.setter
    def return_delay_time(self, rtd):
        if rtd < 0 or rtd > 254:
            raise ValueError("return_delay_time must be in range 0-254")
        self.write_value(5, rtd // 2, 1)
        self._return_delay_time = rtd

    @property
    def angle_limit_cw(self):
        """Angle limit in degrees, CW side. 0 - 300."""
        return self._angle_limit_cw

    @angle_limit_cw.setter
    def angle_limit_cw(self, angle):
        rawval = math.floor(angle * 3.4133332284757363)
        self.write_value(6, rawval, 2)

    @property
    def angle_limit_ccw(self):
        """Angle limit in degrees, CCW side. 0 - 300."""
        return self._angle_limit_ccw

    @angle_limit_ccw.setter
    def angle_limit_ccw(self, angle):
        rawval = math.floor(angle * 3.4133332284757363)
        self.write_value(8, rawval, 2)

    @property
    def min_voltage_limit(self):
        """Minimum voltage limit, volts."""
        return self._min_voltage_limit

    @min_voltage_limit.setter
    def min_voltage_limit(self, voltage):
        self.write_value(12, math.floor(voltage * 10), 1)
        self._min_voltage_limit = voltage

    @property
    def max_voltage_limit(self):
        """Maximum voltage limit, volts."""
        return self._max_voltage_limit

    @max_voltage_limit.setter
    def max_voltage_limit(self, voltage):
        self.write_value(13, math.floor(voltage * 10), 1)
        self._max_voltage_limit = voltage

    @property
    def max_torque(self):
        """Maximum torque to apply, 0-100%."""
        return self._max_torque

    @max_torque.setter
    def max_torque(self, percent):
        self.write_value(14, math.ceil(percent * 10.23), 2)
        self._max_torque = percent

    def enable_torque(self, on=True):
        if on:
            self.write_value(24, 1, 1)
        else:
            self.write_value(24, 0, 1)

    @property
    def goal_position(self):
        """Goal position, from 0 to 300 degrees."""
        rawval, = struct.unpack("<H", self.read_value(30, 2))
        return float(math.ceil(rawval / 3.4133332284757363))

    @goal_position.setter
    def goal_position(self, degrees):
        rawval = math.floor(degrees * 3.4133332284757363)
        self.write_value(30, rawval, 2)

    @property
    def status_return_level(self):
        """When to return a status packet."""
        return self._status_return_level

    @status_return_level.setter
    def status_return_level(self, new):
        new = StatusReturnLevel(new)
        self.write_value(16, int(new), 1)


class StatusReturnLevel(enum.IntEnum):
    """Possible values for status_return_level."""
    PingOnly = 0
    PingAndRead = 1
    All = 2


_BAUD_CODES = {
    1: 1_000_000,
    3: 500_000,
    4: 400_000,
    7: 250_000,
    9: 200_000,
    16: 115_200,
    34: 57_600,
    103: 19_200,
    207: 9600,
}

_BAUD_CODES_REV = dict([(v, k) for k, v in _BAUD_CODES.items()])


_MOTORS = {
    "AX-18A": DynamixelAX18A,
    18: DynamixelAX18A,
}


class SerialInterface:
    """Interface that a motor, or a set of motors, is connected to."""
    def __init__(self, chardevice="/dev/ttyUSB0", baud=57600):
        self.chardevice = chardevice
        self.baud = baud
        self._ser = None

    def open(self, chardevice=None, baud=None):
        devicenode = chardevice or self.chardevice
        if baud is not None:
            self.baud = int(baud)
        self._ser = serial.SerialPort(fname=devicenode, config=str(self.baud))

    def close(self):
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def find_motor(self, motorid, baud=None):
        """Given a motor ID, find the handler class for that model."""
        baud = baud or self.baud
        if self._ser is None:
            self.open(baud=baud)
        # Try protocol 1 first
        protocol = Protocol1(self._ser)
        protocol.send_message(motorid, Instruction.Read, bytes([0, 2]))
        model, = struct.unpack("<H", protocol.read_response())
        return self.get_motor(model, motorid)
        # TODO protocol 2

    def get_motor(self, motortype, motorid, baud=57600):
        """Provide a known motor model and ID.

        Return a motor controller instance.
        """
        baud = baud or self.baud
        mclass = _MOTORS.get(motortype)
        if mclass is None:
            raise UnsupportedModelError("Model {} is not yet supported".format(motortype))
        if self._ser is None:
            self.open(baud=baud)
        return mclass(self._ser, motorid)


if __name__ == "__main__":
    import time
    interface = SerialInterface(baud=1000000)
    m = interface.find_motor(1)
    m.ping()
    # m.read_ram()
    print("baud:", m.baud)
    print("angle limits: CCW:", m.angle_limit_ccw, "CW:", m.angle_limit_cw)
    m.max_torque = 50.
    print("max_torque:", m.max_torque)
    print("goal_position:", m.goal_position, "setting...")
    m.goal_position = 0.
    time.sleep(5)
    print("goal_position:", m.goal_position)
    m.goal_position = 150.
    time.sleep(5)
    print("goal_position:", m.goal_position)
    m.goal_position = 300.
    time.sleep(5)
    print("goal_position:", m.goal_position)
    m.goal_position = 0.
    # m.enable_torque()
    # time.sleep(5)
    del m
    interface.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
