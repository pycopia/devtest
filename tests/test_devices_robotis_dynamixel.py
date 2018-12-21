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

"""Test cases for Dynamixel module.

Set environment variable DYNAMIXEL_MOTOR_ID to the motor id you want to test.
Without that, these tests are skipped.
"""

import os

import pytest

from devtest.os import time
from devtest.devices.robotis import dynamixel


@pytest.fixture(scope="module")
def motor(request):
    mid = int(os.environ.get("DYNAMIXEL_MOTOR_ID"))
    baud = int(os.environ.get("DYNAMIXEL_MOTOR_BAUD", 1000000))
    chardevice = os.environ.get("DYNAMIXEL_DEVICE", "/dev/ttyUSB0")
    interface = dynamixel.SerialInterface(chardevice=chardevice, baud=baud)
    m = interface.find_motor(mid)
    m.ping()
    request.addfinalizer(interface.close)
    return m


def dynamixel_check():
    mid = os.environ.get("DYNAMIXEL_MOTOR_ID")
    if mid is None:
        return False
    try:
        mid = int(mid)
    except (ValueError, TypeError):
        return False
    return True


class TestDynamixelErrorSet:

    def test_create(self):
        for intval in range(256):
            es = dynamixel.DynamixelErrorSet(intval)
            assert int(es) == intval

    def _test_onebit(self, errortype, attribute):
        es = dynamixel.DynamixelErrorSet(errortype)
        assert getattr(es, attribute)
        assert int(es) == errortype
        setattr(es, attribute, False)
        assert not getattr(es, attribute)
        assert int(es) == 0

    def _test_multibit(self, errortype1, attribute1, errortype2, attribute2):
        es = dynamixel.DynamixelErrorSet(errortype1 | errortype2)
        assert getattr(es, attribute1)
        assert getattr(es, attribute2)
        assert int(es) == errortype1 | errortype2
        setattr(es, attribute1, False)
        assert not getattr(es, attribute1)
        assert getattr(es, attribute2)
        assert int(es) == errortype2
        setattr(es, attribute1, True)
        assert getattr(es, attribute2)
        assert getattr(es, attribute1)
        setattr(es, attribute2, False)
        assert not getattr(es, attribute2)
        assert getattr(es, attribute1)
        assert int(es) == errortype1

    def test_instruction(self):
        self._test_onebit(dynamixel.DynamixelErrorType.Instruction,
                          "instruction")
        self._test_multibit(dynamixel.DynamixelErrorType.Instruction,
                            "instruction",
                            dynamixel.DynamixelErrorType.Overload,
                            "overload")
        self._test_multibit(dynamixel.DynamixelErrorType.Instruction,
                            "instruction",
                            dynamixel.DynamixelErrorType.InputVoltage,
                            "input_voltage")

    def test_overload(self):
        self._test_onebit(dynamixel.DynamixelErrorType.Overload,
                          "overload")
        self._test_multibit(dynamixel.DynamixelErrorType.Overload,
                            "overload",
                            dynamixel.DynamixelErrorType.Checksum,
                            "checksum")

    def test_checksum(self):
        self._test_onebit(dynamixel.DynamixelErrorType.Checksum,
                          "checksum")
        self._test_multibit(dynamixel.DynamixelErrorType.Checksum,
                            "checksum",
                            dynamixel.DynamixelErrorType.Range,
                            "range")

    def test_range(self):
        self._test_onebit(dynamixel.DynamixelErrorType.Range,
                          "range")

    def test_overheating(self):
        self._test_onebit(dynamixel.DynamixelErrorType.Overheating,
                          "overheating")

    def test_angle_limit(self):
        self._test_onebit(dynamixel.DynamixelErrorType.AngleLimit,
                          "angle_limit")

    def test_input_voltage(self):
        self._test_onebit(dynamixel.DynamixelErrorType.InputVoltage,
                          "input_voltage")


@pytest.mark.skipif(
    not dynamixel_check(),
    reason="Need attached Dynamixel AX-18A on serial port, and DYNAMIXEL_MOTOR_ID set.")
class TestDynamixelMotor:

    def setup_class(self):
        self.mid = int(os.environ.get("DYNAMIXEL_MOTOR_ID"))
        self.baud = int(os.environ.get("DYNAMIXEL_MOTOR_BAUD", 1000000))
        self.chardevice = os.environ.get("DYNAMIXEL_DEVICE", "/dev/ttyUSB0")

    def test_create_serial(self):
        interface = dynamixel.SerialInterface(chardevice=self.chardevice,
                                              baud=self.baud)
        assert interface.chardevice == self.chardevice
        assert interface.baud == self.baud

    def test_find_motor_by_id(self):
        interface = dynamixel.SerialInterface(chardevice=self.chardevice,
                                              baud=self.baud)
        m = interface.find_motor(self.mid)
        m.ping()
        interface.close()

    def test_move_to(self, motor):
        motor.move_to(0)
        print("current goal_position:", motor.goal_position)
        time.delay(1.0)
        motor.move_to(90)
        time.delay(1.0)
        print("current goal_position:", motor.goal_position)
        motor.move_to(0)
        print("current goal_position:", motor.goal_position)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
