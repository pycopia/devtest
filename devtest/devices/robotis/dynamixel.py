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

"""Dynamixel controllers.

Provides an easy-to-use interface to Dynamixel motors.

All operations and configuration are by properties. Natural units are used,
such percentages, degrees, RPM values, Voltage, etc.

NOTE: Only AX-18A and protocol 1.0 is currently implemented.

Example usage:

    interface = SerialInterface(baud=1000000)
    m = interface.find_motor(1)
    m.ping()
    print("angle limits: CCW:", m.angle_limit_ccw, "CW:", m.angle_limit_cw)
    m.max_torque = 100.  # percent
    print("max_torque:", m.max_torque)

    m.move_to(0)
    print("current goal_position:", m.goal_position)
    time.sleep(1)

    m.move_to(150)  # degrees
    print("current goal_position:", m.goal_position)
    time.sleep(1)

    m.move_to(0)
    print("current goal_position:", m.goal_position)

    del m
    interface.close()

"""

import struct
import enum

from devtest.io import serial
from devtest.os import time
from devtest import timers

# You may use these constants for some properties, where it makes sense.
ON = True
OFF = False


class Direction(enum.IntEnum):
    CCW = 0
    CW = 1024


class StatusReturnLevel(enum.IntEnum):
    """Possible values for status_return_level."""
    PingOnly = 0
    PingAndRead = 1
    All = 2


class DynamixelErrorType(enum.IntEnum):
    Instruction = 0x40
    Overload = 0x20
    Checksum = 0x10
    Range = 0x08
    Overheating = 0x04
    AngleLimit = 0x02
    InputVoltage = 0x01


class Instruction(enum.IntEnum):
    """Protocol instruction byte."""
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


class DynamixelErrorSet:
    """Bitmap of DyanmixelErrorTypes.

    Set or clear Dynamixel error bits by setting the attributes True or False.

    Attributes:
        instruction
        overload
        checksum
        range
        overheating
        angle_limit
        input_voltage
    """

    def __init__(self, flags):
        self._flags = flags & 0xFF

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self._flags)

    def __str__(self):
        return _decode_error(self._flags)

    def __int__(self):
        return self._flags

    def _set_flag(self, errortype):
        self._flags |= errortype

    def _clear_flag(self, errortype):
        self._flags &= (errortype & 0xFF) ^ 0xFF

    @property
    def instruction(self):
        return bool(self._flags & DynamixelErrorType.Instruction)

    @instruction.setter
    def instruction(self, onoff):
        (self._set_flag(DynamixelErrorType.Instruction) if onoff else
         self._clear_flag(DynamixelErrorType.Instruction))

    @property
    def overload(self):
        return bool(self._flags & DynamixelErrorType.Overload)

    @overload.setter
    def overload(self, onoff):
        (self._set_flag(DynamixelErrorType.Overload) if onoff else
         self._clear_flag(DynamixelErrorType.Overload))

    @property
    def checksum(self):
        return bool(self._flags & DynamixelErrorType.Checksum)

    @checksum.setter
    def checksum(self, onoff):
        (self._set_flag(DynamixelErrorType.Checksum) if onoff else
         self._clear_flag(DynamixelErrorType.Checksum))

    @property
    def range(self):
        return bool(self._flags & DynamixelErrorType.Range)

    @range.setter
    def range(self, onoff):
        (self._set_flag(DynamixelErrorType.Range) if onoff else
         self._clear_flag(DynamixelErrorType.Range))

    @property
    def overheating(self):
        return bool(self._flags & DynamixelErrorType.Overheating)

    @overheating.setter
    def overheating(self, onoff):
        (self._set_flag(DynamixelErrorType.Overheating) if onoff else
         self._clear_flag(DynamixelErrorType.Overheating))

    @property
    def angle_limit(self):
        return bool(self._flags & DynamixelErrorType.AngleLimit)

    @angle_limit.setter
    def angle_limit(self, onoff):
        (self._set_flag(DynamixelErrorType.AngleLimit) if onoff else
         self._clear_flag(DynamixelErrorType.AngleLimit))

    @property
    def input_voltage(self):
        return bool(self._flags & DynamixelErrorType.InputVoltage)

    @input_voltage.setter
    def input_voltage(self, onoff):
        (self._set_flag(DynamixelErrorType.InputVoltage) if onoff else
         self._clear_flag(DynamixelErrorType.InputVoltage))


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
            return "{}: {}".format(self.__class__.__name__, _decode_error(flags))
        else:
            # This should never be instantiated if error flags was zero.
            return "{}: No error (fix your code).".format(self.__class__.__name__)


def _decode_error(flags):
    if flags == 0:
        return "(empty)"
    errorlist = []
    for et in DynamixelErrorType:
        if flags & et.value:
            errorlist.append(et.name)
    return "(" + " | ".join(errorlist) + ")"


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

    def __init__(self, serialdevice, motorid):
        self._protocol = Protocol1(serialdevice)
        self.motorid = motorid
        self._wheel_mode = None
        self._multiturn_mode = None
        self._model = None
        self._version = None
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
        """Send Ping to device.

        Returns True if alive, returns False otherwise.
        """
        self._protocol.send_message(self.motorid, Instruction.Ping, b'')
        try:
            time.iotimeout(self._protocol.read_response, timeout=5.0)
        except TimeoutError:
            return False
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

    def register_write_value(self, address, value, length):
        fmt = {1: "BB", 2: "<BH", 4: "<BI"}[length]
        bval = struct.pack(fmt, address, value)
        self._protocol.send_message(self.motorid, Instruction.RegWrite, bval)
        if self._status_return_level == StatusReturnLevel.All:
            self._protocol.read_response()

    def action(self):
        """Perform registered command."""
        self._protocol.send_message(0xFE, Instruction.Action, b"")

    def _read_ram(self, structure, offset):
        raw = self.read_value(offset, structure.size)
        if len(raw) != structure.size:
            raise DynamixelError("bad read of RAM")
        return structure.unpack(raw)

    def _read_eeprom(self, structure):
        raw = self.read_value(0, structure.size)
        if len(raw) != structure.size:
            raise DynamixelError("bad read of EEPROM")
        return structure.unpack(raw)

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
        if rtd < 0 or rtd > 508:
            raise ValueError("return_delay_time must be in range 0-508 uS")
        self.write_value(5, rtd // 2, 1)
        self._return_delay_time = rtd

    @property
    def wheel_mode(self):
        """Check for wheel mode.

        Wheel mode is indicated by both Angle Limit CW and Angle Limit CCW are
        both zero.
        """
        if self._wheel_mode is None:
            angle_limit_cw = int.from_bytes(self.read_value(6, 2), byteorder="little")
            angle_limit_ccw = int.from_bytes(self.read_value(8, 2), byteorder="little")
            self._wheel_mode = angle_limit_cw == 0 and angle_limit_ccw == 0
        return self._wheel_mode

    @property
    def multiturn_mode(self):
        """Check for multi-turn mode.

        Multiturn mode is indicated by both Angle Limit CW and Angle Limit CCW are
        both 4095.
        """
        if self._multiturn_mode is None:
            angle_limit_cw = int.from_bytes(self.read_value(6, 2), byteorder="little")
            angle_limit_ccw = int.from_bytes(self.read_value(8, 2), byteorder="little")
            self._multiturn_mode = angle_limit_cw == 4095 and angle_limit_ccw == 4095
        return self._multiturn_mode

    @property
    def min_voltage_limit(self):
        """Minimum voltage limit, volts."""
        return self._min_voltage_limit

    @min_voltage_limit.setter
    def min_voltage_limit(self, voltage):
        self.write_value(12, round(voltage * 10), 1)
        self._min_voltage_limit = voltage

    @property
    def max_voltage_limit(self):
        """Maximum voltage limit, volts."""
        return self._max_voltage_limit

    @max_voltage_limit.setter
    def max_voltage_limit(self, voltage):
        self.write_value(13, round(voltage * 10), 1)
        self._max_voltage_limit = voltage

    @property
    def max_torque(self):
        """Maximum torque to apply, 0-100%."""
        return self._max_torque

    @max_torque.setter
    def max_torque(self, percent):
        self.write_value(14, round(percent * 10.23), 2)
        self._max_torque = percent

    @property
    def status_return_level(self):
        """When to return a status packet."""
        return self._status_return_level

    @status_return_level.setter
    def status_return_level(self, new):
        new = StatusReturnLevel(new)
        self.write_value(16, int(new), 1)
        self._status_return_level = new

    @property
    def alarm_led(self):
        """What errors make the alarm LED blink."""
        return self._alarm_led

    @alarm_led.setter
    def alarm_led(self, errorset: DynamixelErrorSet):
        errorset = DynamixelErrorSet(int(errorset))
        self.write_value(17, int(errorset), 1)
        self._alarm_led = errorset

    @property
    def shutdown(self):
        """What errors that will cause the motor output to become 0%.

        This works by resetting the value of Torque Limit to 0.
        """
        return self._shutdown_info

    @shutdown.setter
    def shutdown(self, errorset: DynamixelErrorSet):
        errorset = DynamixelErrorSet(int(errorset))
        self.write_value(18, int(errorset), 1)
        self._shutdown_info = errorset

    # RAM control table follows
    @property
    def torque(self):
        """Turn the torque value on or off.

        Effectively enables or disables the motor.
        If set True, turns on torque and lock EEPROM.
        If set False, turn off torque, free run state.
        """
        return bool(int.from_bytes(self.read_value(24, 1), byteorder="little"))

    @torque.setter
    def torque(self, onoff):
        self.write_value(24, 1, 1) if onoff else self.write_value(24, 0, 1)

    @property
    def led(self):
        """Turn on or off the LED on Dynamixel.

        If set True, turns on LED.
        If set False, turn off LED.
        """
        return bool(int.from_bytes(self.read_value(25, 1), byteorder="little"))

    @led.setter
    def led(self, onoff):
        self.write_value(25, 1, 1) if onoff else self.write_value(25, 0, 1)

    @property
    def moving_speed(self):
        """Moving speed to goal postion. Depends on operating mode.

        Set both angle_limit_cw and angle_limit_ccw to zero to enable wheel
        mode.

        See: http://emanual.robotis.com/docs/en/dxl/ax/ax-18a/#moving-speed

        Wheel mode:
            Unit is percent of max speed.

        Joint mode:
            Unit is RPM, from 0 to 114.
            Value of 0 is special, it means maximum RPM.
        """
        if self.wheel_mode:
            rawval = int.from_bytes(self.read_value(32, 2), byteorder="little")
            return rawval  # TODO(dart)
        else:
            rawval = int.from_bytes(self.read_value(32, 2), byteorder="little")
            if rawval == 0:
                return 115.  # Maximum RPM
            else:
                return round(rawval / 8.973684210526315, 2)

    @moving_speed.setter
    def moving_speed(self, rpm_or_percent):
        if self.wheel_mode:
            pass  # TODO(dart)
        else:  # Joint mode, RPM unit
            if rpm_or_percent < 0:
                raise ValueError("moving speed must be 1 - 115 RPM")
            if rpm_or_percent >= 114:
                self.write_value(32, 0, 2)
            else:
                rawval = round(rpm_or_percent * 8.973684210526315)  # as RPM
                if rawval > 1023:
                    rawval = 1023
                self.write_value(32, rawval, 2)

    @property
    def torque_limit(self):
        """Maximum torque applied, as percent of max.

        If it is zero the motor is disabled.
        """
        rawval = int.from_bytes(self.read_value(34, 2), byteorder="little")
        return round(rawval / 10.23, 2)

    @torque_limit.setter
    def torque_limit(self, percent):
        self.write_value(34, round(percent * 10.23), 2)

    @property
    def present_speed(self):
        """Present speed, in RPM for Joint Mode, in percent of max for Wheel
        mode."""
        rawval = int.from_bytes(self.read_value(38, 2), byteorder="little")
        direction = rawval & 0x800
        if self.wheel_mode:
            return Direction(direction), round((rawval & 0x3FF) / 10.23, 2)
        else:
            return Direction(direction), round((rawval & 0x3FF) * 0.111111, 2)

    @property
    def present_load(self):
        """Present load, in percent of max torque."""
        rawval = int.from_bytes(self.read_value(40, 2), byteorder="little")
        direction = rawval & 0x800
        return Direction(direction), round((rawval & 0x3FF) / 10.23, 2)

    @property
    def present_voltage(self):
        """Present voltage applied."""
        rawval = int.from_bytes(self.read_value(42, 1), byteorder="little")
        return rawval / 10.

    @property
    def present_temperature(self):
        """Present temperature in degrees C."""
        return int.from_bytes(self.read_value(43, 1), byteorder="little")

    @property
    def has_registered(self):
        """Indicates if a registered instruction has been received."""
        return bool(int.from_bytes(self.read_value(44, 1), byteorder="little"))

    @property
    def is_moving(self):
        """Indicates if motor is currently moving."""
        return bool(int.from_bytes(self.read_value(46, 1), byteorder="little"))

    @property
    def is_locked(self):
        """Indicates EEPROM area can be modified."""
        return bool(int.from_bytes(self.read_value(47, 1), byteorder="little"))

    def lock(self):
        """Lock EEPROM area. Power must be cycled to change it back."""
        self.write_value(47, 1, 1)

    @property
    def punch(self):
        """Minimum current to drive motor.

        NOTE: manual is not clear on the units.
        """
        rawval = int.from_bytes(self.read_value(48, 2), byteorder="little")
        return rawval

    @punch.setter
    def punch(self, current):
        current = int(current)
        if current >= 0x20 or current <= 0x3FF:
            self.write_value(48, current, 2)


class DynamixelAX18A(Dynamixel):
    """A Dynamixel model AX-18A."""

    EEPROM = struct.Struct("<H4BHH4BH3B")
    RAM = struct.Struct("<6B6H6BH")  # offset 24
    RAM_OFFSET = 24
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

    def read_eeprom(self):
        resp = self._read_eeprom(DynamixelAX18A.EEPROM)
        (self._model, self._version, self.motorid, baud, rtd, angle_limit_cw,
         angle_limit_ccw, _, temp_limit, min_v_limit, max_v_limit, max_torque,
         status_return, alarm_led, shutdown_info) = resp
        self._baudcode = baud
        self._return_delay_time = 2 * rtd  # usec
        self._wheel_mode = angle_limit_cw == 0 and angle_limit_ccw == 0
        self._angle_limit_cw = round(angle_limit_cw * 0.2932551319648094, 2)
        self._angle_limit_ccw = round(angle_limit_ccw * 0.2932551319648094, 2)
        self._min_voltage_limit = min_v_limit / 10.
        self._max_voltage_limit = max_v_limit / 10.
        self._max_torque = round(max_torque / 10.23, 2)
        self._status_return_level = StatusReturnLevel(status_return)
        self._alarm_led = DynamixelErrorSet(alarm_led)
        self._shutdown_info = DynamixelErrorSet(shutdown_info)

    @property
    def angle_limit_cw(self):
        """Angle limit in degrees, CW side. 0 - 300."""
        return self._angle_limit_cw

    @angle_limit_cw.setter
    def angle_limit_cw(self, angle):
        rawval = round(angle / 0.2932551319648094)
        self.write_value(6, rawval, 2)
        self._angle_limit_cw = angle
        self._wheel_mode = None

    @property
    def angle_limit_ccw(self):
        """Angle limit in degrees, CCW side. 0 - 300."""
        return self._angle_limit_ccw

    @angle_limit_ccw.setter
    def angle_limit_ccw(self, angle):
        rawval = round(angle / 0.2932551319648094)
        self.write_value(8, rawval, 2)
        self._angle_limit_ccw = angle
        self._wheel_mode = None

    # RAM control table follows
    @property
    def compliance_margin_cw(self):
        """Compliance margin CW, from 1 to 75 degrees."""
        rawval = int.from_bytes(self.read_value(26, 1), byteorder="little")
        return round(rawval / 3.4133332284757363, 2)

    @compliance_margin_cw.setter
    def compliance_margin_cw(self, degrees):
        rawval = round(degrees * 3.4133332284757363)
        self.write_value(26, rawval, 1)

    @property
    def compliance_margin_ccw(self):
        """Compliance margin CCW, from 1 to 75 degrees."""
        rawval = int.from_bytes(self.read_value(27, 1), byteorder="little")
        return round(rawval / 3.4133332284757363, 2)

    @compliance_margin_ccw.setter
    def compliance_margin_ccw(self, degrees):
        rawval = round(degrees * 3.4133332284757363)
        self.write_value(27, rawval, 1)

    @property
    def compliance_slope_cw(self):
        """Sets the level of Torque near the goal position, CW direction.

        Compliance Slope is set in 7 steps, the higher the value, the more
        flexibility is obtained. Data representative value is actually used
        value. That is, even if the value is set to 25, 16 is used internally as
        the representative value.

        Step    Data Value              Data Representative Value
        1       0(0x00) ~ 3(0x03)       2(0x02)
        2       4(0x04) ~ 7(0x07)       4(0x04)
        3       8(0x08)~15(0x0F)        8(0x08)
        4       16(0x10)~31(0x1F)       16(0x10)
        5       32(0x20)~63(0x3F)       32(0x20)
        6       64(0x40)~127(0x7F)      64(0x40)
        7       128(0x80)~254(0xFE)     128(0x80)
        """
        return int.from_bytes(self.read_value(28, 1), byteorder="little")

    @compliance_slope_cw.setter
    def compliance_slope_cw(self, value):
        self.write_value(28, int(value), 1)

    @property
    def compliance_slope_ccw(self):
        """Sets the level of Torque near the goal position, CCW direction.

        See compliance_slope_cw for more info.
        """
        return int.from_bytes(self.read_value(29, 1), byteorder="little")

    @compliance_slope_ccw.setter
    def compliance_slope_ccw(self, value):
        self.write_value(29, int(value), 1)

    @property
    def goal_position(self):
        """Goal position, from 0 to 300 degrees."""
        rawval = int.from_bytes(self.read_value(30, 2), byteorder="little")
        return round(rawval * 0.2932551319648094, 2)

    @goal_position.setter
    def goal_position(self, angle):
        rawval = round(angle / 0.2932551319648094)
        self.write_value(30, rawval, 2)

    @property
    def present_position(self):
        """Present position, in degrees."""
        rawval = int.from_bytes(self.read_value(36, 2), byteorder="little")
        return round(rawval * 0.2932551319648094, 2)

    def move_to(self, goal):
        """Move to <goal> angle. Blocks until complete."""
        if not self.wheel_mode:
            self.goal_position = goal
            # Use raw values inside methods for slightly better performance
            rawgoal = round(goal / 0.2932551319648094)
            # Reported and requested values can differ slightly
            bot = max(rawgoal - 2, 0)
            top = min(rawgoal + 2, 1023)
            present_position = int.from_bytes(self.read_value(36, 2), byteorder="little")
            while present_position < bot or present_position > top:
                timers.nanosleep(0.01)
                present_position = int.from_bytes(self.read_value(36, 2), byteorder="little")


class DynamixelMX64A(Dynamixel):
    """A Dynamixel model MX-64A."""

    EEPROM = struct.Struct("<H4BHH4BH4BhB")
    RAM = struct.Struct("<6B6H6B2H16BHBHB")  # offset 24
    RAM_OFFSET = 24
    # Control Table of EEPROM Area
    # Address | Size | Data Name | Description | Access | Initial Value |
    # 0 | 2 | Model Number | Model Number | R | 310 |
    # 2 | 1 | Firmware Version | Firmware Version | R | - |
    # 3 | 1 | ID | DYNAMIXEL ID | RW | 1 |
    # 4 | 1 | Baud Rate | Communication Speed | RW | 34 |
    # 5 | 1 | Return Delay Time | Response Delay Time | RW | 250 |
    # 6 | 2 | CW Angle Limit | Clockwise Angle Limit | RW | 0 |
    # 8 | 2 | CCW Angle Limit | Counter-Clockwise Angle Limit | RW | 4,095 |
    # 10 | 1 unused
    # 11 | 1 | Temperature Limit | Maximum Internal Temperature Limit | RW | 80 |
    # 12 | 1 | Min Voltage Limit | Minimum Input Voltage Limit | RW | 60 |
    # 13 | 1 | Max Voltage Limit | Maximum Input Voltage Limit | RW | 240 |
    # 14 | 2 | Max Torque | Maximun Torque | RW | 1023 |
    # 16 | 1 | Status Return Level | Select Types of Status Return | RW | 2 |
    # 17 | 1 | Alarm LED | LED for Alarm | RW | 36 |
    # 18 | 1 | Shutdown | Shutdown Error Information | RW | 36 |
    # 19 | 1 unused
    # 20 | 2 | Multi Turn Offset | Adjust Position with Offset | RW | 0 |
    # 22 | 1 | Resolution Divider | Divider for Position Resolution | RW | 1 |

    # Control Table of RAM Area
    # Address | Size | Data Name | Description | Access | Initial Value |
    # 24 | 1 | Torque Enable | Motor Torque On/Off | RW | 0 |
    # 25 | 1 | LED | Status LED On/Off | RW | 0 |
    # 26 | 1 | D Gain | Derivative Gain | RW | 0 |
    # 27 | 1 | I Gain | Integral Gain | RW | 0 |
    # 28 | 1 | P Gain | Proportional Gain | RW | 32 |
    # 29 | 1 unused
    # 30 | 2 | Goal Position | Desired Position | RW | - |
    # 32 | 2 | Moving Speed | RW | - |
    # 34 | 2 | Torque Limit | RW | ADD 14&15 |
    # 36 | 2 | Present Position | Present Position | R | - |
    # 38 | 2 | Present Speed | Present Speed | R | - |
    # 40 | 2 | Present Load | Present Load | R | - |
    # 42 | 1 | Present Voltage | Present Voltage | R | - |
    # 43 | 1 | Present Temperature | Present Temperature | R | - |
    # 44 | 1 | Registered | If Instruction is registered | R | 0 |
    # 45 | 1 unused
    # 46 | 1 | Moving | Movement Status | R | 0 |
    # 47 | 1 | Lock | Locking EEPROM | RW | 0 |
    # 48 | 2 | Punch | Minimum Current Threshold | RW | 0 |
    # 50 | 2 | Realtime Tick | Count Time in millisecond | R | 0 |
    # 52 | 16 unused
    # 68 | 2 | Current | Consuming Current | RW | 0 |
    # 70 | 1 | Torque Ctrl Mode Enable | Torque Control Mode On/Off | RW | 0 |
    # 71 | 2 | Goal Torque | Goal Torque | RW | 0 |
    # 73 | 1 | Goal Acceleration | Goal Acceleration | RW | 0 |

    def read_eeprom(self):
        resp = self._read_eeprom(DynamixelMX64A.EEPROM)
        (self._model, self._version, self.motorid, baud, rtd, angle_limit_cw,
         angle_limit_ccw, _, temp_limit, min_v_limit, max_v_limit, max_torque,
         status_return, alarm_led, shutdown_info, _, multiturn_offset, resolution_divider) = resp
        self._baudcode = baud
        self._return_delay_time = 2 * rtd  # usec
        self._wheel_mode = angle_limit_cw == 0 and angle_limit_ccw == 0
        self._multiturn_mode = angle_limit_cw == 4095 and angle_limit_ccw == 4095
        self._angle_limit_cw = round(angle_limit_cw * 0.2932551319648094, 2)
        self._angle_limit_ccw = round(angle_limit_ccw * 0.2932551319648094, 2)
        self._min_voltage_limit = min_v_limit / 10.
        self._max_voltage_limit = max_v_limit / 10.
        self._max_torque = round(max_torque / 10.23, 2)
        self._status_return_level = StatusReturnLevel(status_return)
        self._alarm_led = DynamixelErrorSet(alarm_led)
        self._shutdown_info = DynamixelErrorSet(shutdown_info)
        self._multiturn_offset = multiturn_offset
        self._resolution_divider = resolution_divider

    @property
    def angle_limit_cw(self):
        """Angle limit in degrees, CW side. 0 - 360."""
        return self._angle_limit_cw

    @angle_limit_cw.setter
    def angle_limit_cw(self, angle):
        rawval = round(angle / 0.08791208791208792)
        self.write_value(6, rawval, 2)
        self._angle_limit_cw = angle
        self._wheel_mode = None
        self._multiturn_mode = None

    @property
    def angle_limit_ccw(self):
        """Angle limit in degrees, CCW side. 0 - 360."""
        return self._angle_limit_ccw

    @angle_limit_ccw.setter
    def angle_limit_ccw(self, angle):
        rawval = round(angle / 0.08791208791208792)
        self.write_value(8, rawval, 2)
        self._angle_limit_ccw = angle
        self._wheel_mode = None
        self._multiturn_mode = None

    @property
    def multiturn_offset(self):
        """Adjusts offset position.

        Only meaningful in multi-turn mode.
        """
        return self._multiturn_offset

    @multiturn_offset.setter
    def multiturn_offset(self, offset):
        self.write_value(20, offset, 2)
        self._multiturn_offset = offset

    @property
    def resolution_divider(self):
        """It allows the user to change Dynamixel’s resolution.

        Only meaningful in multi-turn mode.
        """
        return self._resolution_divider

    @resolution_divider.setter
    def resolution_divider(self, value):
        if value < 1 or value > 4:
            raise ValueError("The resolution_divider must be between 1 and 4.")
        self.write_value(22, value, 1)
        self._resolution_divider = value

    # RAM control table follows
    @property
    def goal_position(self):
        """Goal position, from 0 to 360 degrees."""
        rawval = int.from_bytes(self.read_value(30, 2), byteorder="little")
        return round(rawval * 0.08791208791208792, 2)

    @goal_position.setter
    def goal_position(self, angle):
        rawval = round(angle / 0.08791208791208792)
        self.write_value(30, rawval, 2)

    @property
    def present_position(self):
        """Present position, in degrees (0 to 360)."""
        rawval = int.from_bytes(self.read_value(36, 2), byteorder="little")
        return round(rawval * 0.08791208791208792, 2)

    def move_to(self, goal):
        """Move to <goal> angle. Blocks until complete."""
        if not self.wheel_mode and not self.multiturn_mode:
            self.goal_position = goal
            # Use raw values inside methods for better performance
            rawgoal = round(goal / 0.08791208791208792)
            # Reported and requested values can differ slightly
            bot = max(rawgoal - 2, 0)
            top = min(rawgoal + 2, 4095)
            present_position = int.from_bytes(self.read_value(36, 2), byteorder="little")
            while present_position < bot or present_position > top:
                timers.nanosleep(0.01)
                present_position = int.from_bytes(self.read_value(36, 2), byteorder="little")


_BAUD_CODES = {
    1: 1_000_000,
    3: 500_000,
    4: 400_000,
    7: 250_000,
    9: 200_000,
    16: 115_200,
    34: 57_600,
    103: 19_200,
    207: 9_600,
    250: 2_250_000,
    251: 2_500_000,
    252: 3_000_000,
}

_BAUD_CODES_REV = dict([(v, k) for k, v in _BAUD_CODES.items()])


# Maps both human-friendly name for scripting use, and product ID number for
# find method use.
_MOTORS = {
    "AX-18A": DynamixelAX18A,
    18: DynamixelAX18A,
    "MX-64A": DynamixelMX64A,
    310: DynamixelMX64A,
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
        try:
            resp = time.iotimeout(protocol.read_response, timeout=5.0)
        except TimeoutError as to:
            raise DynamixelError("Did not find ID {}".format(motorid)) from to
        model, = struct.unpack("<H", resp)
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

    def perform_action(self):
        """Perform registered command on all devices."""
        if self._ser is not None:
            protocol = Protocol1(self._ser)
            protocol.send_message(0xFE, Instruction.Action, b"")


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
