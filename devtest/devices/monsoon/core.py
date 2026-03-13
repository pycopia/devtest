"""Shared Monsoon objects."""

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Portions of this code were copied from the Monsoon open-source Python
# interface. It has the following license.

# Copyright 2017 Monsoon Solutions, Inc
#
# Permission is hereby granted, free of charge, to any person obtaining a copy o
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import interface

# pylint: disable=too-many-instance-attributes,attribute-defined-outside-init


class HardwareModel(enum.IntEnum):
    """The hardware model or type."""

    UNKNOWN = 0
    LVPM = 1
    HVPM = 2


# pylint: disable=invalid-name
class USBPassthrough(enum.IntEnum):
    """Values for setting or retrieving the USB Passthrough mode."""

    Off = 0
    On = 1
    Auto = 2


class VoltageChannel(enum.IntEnum):
    """Values for setting or retrieving the Voltage Channel."""

    MainAndUSB = 0
    MainAndAux = 1


class ControlCodes(enum.IntEnum):
    """Monsoon control codes."""

    USB_REQUEST_START = 0x02
    USB_REQUEST_STOP = 0x03
    USB_SET_VALUE = 0x01
    USB_REQUEST_RESET_TO_BOOTLOADER = 0xFF


class OpCodes(enum.Enum):
    """USB Control Transfer operation codes: (code, struct_format)"""

    # Internal voltage calibration, affects accuracy of setHVMainVoltage.
    CalibrateMainVoltage = (0x03, None)
    DacCalHigh = (0x89, "<H")  # 4.096V ADC Reference Calibration
    DacCalLow = (0x88, "<H")  # 2.5V ADC Reference Calibration
    FirmwareVersion = (0xC0, "<H")  # Read-only, gets the firmware version
    GetSerialNumber = (0x42, "<I")
    GetStartStatus = (0xC4, "B")
    HardwareModel = (0x45, "<H")  # 0 = unknown, 1 = LV, 2 = HV
    ProtocolVersion = (0xC1, "B")  # Read-only, gets the Protocol version
    ResetPowerMonitor = (0x05, None)  # Reset the PIC.  Causes disconnect.
    # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    SetAuxCoarseResistorOffset = (0x13, "b")
    SetAuxCoarseScale = (0x1F, "<H")  # HVPM Calibration value, 32-bits, unsigned
    # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    SetAuxFineResistorOffset = (0x0E, "b")
    SetAuxFineScale = (0x1E, "<H")  # HVPM Calibration value, 32-bits, unsigned
    # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetMainCoarseResistorOffset = (0x11, "b")
    SetMainCoarseScale = (0x1B, "<H")  # HVPM Calibration value, 32-bits, unsigned
    SetMainCoarseZeroOffset = (0x26, "<h")  # Zero-level offset
    # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetMainFineResistorOffset = (0x02, "b")
    SetMainFineScale = (0x1A, "<H")  # HVPM Calibration value, 32-bits, unsigned
    SetMainFineZeroOffset = (0x25, "<h")  # Zero-level offset
    SetMainVoltage = (0x41, None)  # Voltage = value * 1048576
    # Sets power-up current limit.
    # HV Amps = 15.625*(1.0-powerupCurrentLimit/65535)
    # LV amps = 8.0*(1.0-powerupCurrentLimit/1023.0)
    SetPowerUpCurrentLimit = (0x43, "<H")
    # time in milliseconds that the powerup current limit is in effect.
    SetPowerupTime = (0x0C, "B")
    # Sets runtime current limit
    # HV Amps = 15.625*(1.0-powerupCurrentLimit/65535)
    # LV amps = 8.0*(1.0-powerupCurrentLimit/1023.0)
    SetRunCurrentLimit = (0x44, "<H")
    SetTemperatureLimit = (0x29, "<H")  # Temperature limit in Signed Q7.8 format
    # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBCoarseResistorOffset = (0x12, "b")
    SetUSBCoarseScale = (0x1D, "<H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBCoarseZeroOffset = (0x28, "<h")  # Zero-level offset
    # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBFineResistorOffset = (0x0D, "b")
    SetUSBFineScale = (0x1C, "<H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBFineZeroOffset = (0x27, "<h")  # Zero-level offset
    # Sets USB Passthrough mode according to value. Off = 0, On = 1, Auto = 2
    SetUSBPassthroughMode = (0x10, "B")
    # Sets voltage channel:
    # Value 00 = Main & USB voltage measurements.
    # Value 01 = Main & Aux voltage measurements
    SetVoltageChannel = (0x23, "B")
    Stop = (0xFF, None)


class MonsoonInfo:
    """Values stored in the Power Monitor EEPROM.

  Each corresponds to an opcode.
  """

    AuxCoarseResistorOffset = 0.0  # signed, ohms = 0.10 + 0.0001*offset
    AuxCoarseScale = 0  # HVPM Calibration value, 32-bits, unsigned
    AuxFineResistorOffset = 0.0  # signed, ohms = 0.10 + 0.0001*offset
    AuxFineScale = 0  # HVPM Calibration value, 32-bits, unsigned
    DacCalHigh = 0
    DacCalLow = 0
    FirmwareVersion = 0  # Firmware version number.
    HardwareModel = HardwareModel(0)
    MainCoarseResistorOffset = 0.0  # signed, ohms = 0.05 + 0.0001*offset
    MainCoarseScale = 0  # HVPM Calibration value, 32-bits, unsigned
    MainCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    MainFineResistorOffset = 0.0  # signed, ohms = 0.05 + 0.0001*offset
    MainFineScale = 0  # HVPM Calibration value, 32-bits, unsigned
    MainFineZeroOffset = 0  # HVPM-only, Zero-level offset
    # Max current during startup before overcurrent protection circuit activates.
    # LVPM is 0-8A, HVPM is 0-15A.
    PowerupCurrentLimit = 0
    PowerupTime = 0  # Time in ms the powerupcurrent limit will be used.
    ProtocolVersion = 0  # Protocol version number.
    # Max current during runtime before overcurrent protection circuit activates.
    # LVPM is 0-8A, HVPM is 0-15A.
    RuntimeCurrentLimit = 0
    SerialNumber = 0  # Unit's serial number.
    TemperatureLimit = 0  # Temperature limit in Signed Q7.8 format
    UsbCoarseResistorOffset = 0.0  # signed, ohms = 0.05 + 0.0001*offset
    UsbCoarseScale = 0  # HVPM Calibration value, 32-bits, unsigned
    UsbCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    UsbFineResistorOffset = 0.0  # signed, ohms = 0.05 + 0.0001*offset
    UsbFineScale = 0  # HVPM Calibration value, 32-bits, unsigned
    UsbFineZeroOffset = 0.0  # HVPM-only, Zero-level offset
    UsbPassthroughMode = USBPassthrough(0)  # Off = 0, On = 1, Auto = 2
    VoltageChannel = VoltageChannel(0)

    def populate(self, dev: "interface.HVPM"):
        """Populate this instance with information from the device."""
        self.SerialNumber = dev.serial
        self.Voltage = dev.voltage
        self.MainVoltageScale = dev.main_voltage_scale
        self.USBVoltageScale = dev.usb_voltage_scale
        self.ADCRatio = dev.ADCRatio
        self.FineThreshold = dev.fine_threshold
        self.AuxFineThreshold = dev.aux_fine_threshold
        self.AuxCoarseResistorOffset = float(dev.get_value(OpCodes.SetAuxCoarseResistorOffset))
        self.AuxCoarseScale = int(dev.get_value(OpCodes.SetAuxCoarseScale))
        self.AuxFineResistorOffset = float(dev.get_value(OpCodes.SetAuxFineResistorOffset))
        self.AuxFineScale = int(dev.get_value(OpCodes.SetAuxFineScale))
        self.DacCalHigh = dev.get_value(OpCodes.DacCalHigh)
        self.DacCalLow = dev.get_value(OpCodes.DacCalLow)
        self.FirmwareVersion = dev.get_value(OpCodes.FirmwareVersion)
        self.HardwareModel = HardwareModel(dev.get_value(OpCodes.HardwareModel))
        self.MainCoarseResistorOffset = float(dev.get_value(OpCodes.SetMainCoarseResistorOffset))
        self.MainCoarseScale = int(dev.get_value(OpCodes.SetMainCoarseScale))
        self.MainCoarseZeroOffset = int(dev.get_value(OpCodes.SetMainCoarseZeroOffset))
        self.MainFineResistorOffset = float(dev.get_value(OpCodes.SetMainFineResistorOffset))
        self.MainFineScale = int(dev.get_value(OpCodes.SetMainFineScale))
        self.MainFineZeroOffset = int(dev.get_value(OpCodes.SetMainFineZeroOffset))
        self.PowerupCurrentLimit = _amps_from_raw(dev.get_value(OpCodes.SetPowerUpCurrentLimit))
        self.PowerupTime = dev.get_value(OpCodes.SetPowerupTime)
        self.ProtocolVersion = dev.get_value(OpCodes.ProtocolVersion)
        self.RuntimeCurrentLimit = _amps_from_raw(dev.get_value(OpCodes.SetRunCurrentLimit))
        self.TemperatureLimit = _degrees_from_raw(dev.get_value(OpCodes.SetTemperatureLimit))
        self.UsbCoarseResistorOffset = float(dev.get_value(OpCodes.SetUSBCoarseResistorOffset))
        self.UsbCoarseScale = int(dev.get_value(OpCodes.SetUSBCoarseScale))
        self.UsbCoarseZeroOffset = int(dev.get_value(OpCodes.SetUSBCoarseZeroOffset))
        self.UsbFineResistorOffset = float(dev.get_value(OpCodes.SetUSBFineResistorOffset))
        self.UsbFineScale = int(dev.get_value(OpCodes.SetUSBFineScale))
        self.UsbFineZeroOffset = float(dev.get_value(OpCodes.SetUSBFineZeroOffset))
        self.UsbPassthroughMode = USBPassthrough(dev.get_value(OpCodes.SetUSBPassthroughMode))
        self.VoltageChannel = VoltageChannel(dev.get_value(OpCodes.SetVoltageChannel))

    def __str__(self):
        s = []
        s.append(f"SerialNumber: {self.SerialNumber}")
        s.append(f"Voltage: {self.Voltage}")
        s.append(f"MainVoltageScale: {self.MainVoltageScale}")
        s.append(f"USBVoltageScale: {self.USBVoltageScale}")
        s.append(f"ADCRatio: {self.ADCRatio}")
        s.append(f"AuxCoarseResistorOffset: {self.AuxCoarseResistorOffset}")
        s.append(f"AuxCoarseScale: {self.AuxCoarseScale}")
        s.append(f"AuxFineResistorOffset: {self.AuxFineResistorOffset}")
        s.append(f"AuxFineScale: {self.AuxFineScale}")
        s.append(f"DacCalHigh: {self.DacCalHigh}")
        s.append(f"DacCalLow: {self.DacCalLow}")
        s.append(f"FirmwareVersion: {self.FirmwareVersion}")
        s.append(f"HardwareModel: {self.HardwareModel!r}")
        s.append(f"MainCoarseResistorOffset: {self.MainCoarseResistorOffset}")
        s.append(f"MainCoarseScale: {self.MainCoarseScale}")
        s.append(f"MainCoarseZeroOffset: {self.MainCoarseZeroOffset}")
        s.append(f"MainFineResistorOffset: {self.MainFineResistorOffset}")
        s.append(f"MainFineScale: {self.MainFineScale}")
        s.append(f"MainFineZeroOffset: {self.MainFineZeroOffset}")
        s.append(f"PowerupCurrentLimit: {self.PowerupCurrentLimit}")
        s.append(f"PowerupTime: {self.PowerupTime}")
        s.append(f"ProtocolVersion: {self.ProtocolVersion}")
        s.append(f"RuntimeCurrentLimit: {self.RuntimeCurrentLimit}")
        s.append(f"TemperatureLimit: {self.TemperatureLimit}")
        s.append(f"UsbCoarseResistorOffset: {self.UsbCoarseResistorOffset}")
        s.append(f"UsbCoarseScale: {self.UsbCoarseScale}")
        s.append(f"UsbCoarseZeroOffset: {self.UsbCoarseZeroOffset}")
        s.append(f"UsbFineResistorOffset: {self.UsbFineResistorOffset}")
        s.append(f"UsbFineScale: {self.UsbFineScale}")
        s.append(f"UsbFineZeroOffset: {self.UsbFineZeroOffset}")
        s.append(f"UsbPassthroughMode: {self.UsbPassthroughMode!r}")
        s.append(f"VoltageChannel: {self.VoltageChannel!r}")
        return "\n".join(s)


def _amps_from_raw(raw):
    return 15.625 * (raw - 3840.0) / 61695.0


def _raw_from_amps(value):
    return 61695 * (value / 15.625) + 0x0F00


def _degrees_from_raw(value):
    return ((value & 0xFF00) >> 8) + ((value & 0xFF) * 0.00390625)


class BootloaderCommands(enum.IntEnum):
    """Bootloader opcodes.  Used when reflashing the Power Monitor"""

    ReadVersion = 0x00
    ReadFlash = 0x01
    WriteFlash = 0x02
    EraseFlash = 0x03
    ReadEEPROM = 0x04
    WriteEEPROM = 0x05
    ReadConfig = 0x06
    WriteConfig = 0x07
    Reset = 0xFF


class BootloaderMemoryRegions(enum.IntEnum):
    """Memory regions of the PIC18F4550"""

    Flash = 0x00
    IDLocs = 0x20
    Config = 0x30
    EEPROM = 0xF0


class SampleType(enum.IntEnum):
    """Corresponds to the sampletype field from a sample packet."""

    Measurement = 0x00
    ZeroCal = 0x10
    Invalid = 0x20
    RefCal = 0x30


class MeasurementResult:
    """Summary information resulting from any measurement run.

  Returned by measure methods.
  """

    # This object should be kept in core module since it may be pickled, and
    # unpickled in a place without a Monsoon.

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @classmethod
    def from_context_and_handler(cls, ctx, handler):
        """Constructor from a measurement context and handler attributes."""
        return cls(
            handler=handler.__class__.__name__,
            captured=handler.captured,
            dropped=handler.dropped,
            sample_count=handler.sample_count,
            measure_count=handler.measure_count,
            main_current=getattr(handler, "main_current", None),
            main_power=getattr(handler, "main_power", None),
            main_voltage=getattr(handler, "main_voltage", None),
            usb_current=getattr(handler, "usb_current", None),
            usb_power=getattr(handler, "usb_power", None),
            usb_voltage=getattr(handler, "usb_voltage", None),
            aux_current=getattr(handler, "aux_current", None),
            sample_rate=getattr(handler, "sample_rate", 5000),
            start_time=ctx.get("start_time"),
            samplefile=ctx.get("filename"),
            duration=ctx.get("duration"),
            delay=ctx.get("delay", 0),
            passthrough=ctx.get("passthrough", "auto"),
            voltage=ctx["voltage"],
            columns=handler.COLUMNS,
            units=handler.UNITS,
        )

    # pylint: disable=no-member
    def __str__(self):
        s = [f"{self.__class__.__name__} for {self.handler}:"]
        for name in (
                "start_time",
                "duration",
                "captured",
                "dropped",
                "sample_count",
                "measure_count",
                "main_current",
                "main_power",
                "main_voltage",
                "usb_current",
                "usb_power",
                "usb_voltage",
                "aux_current",
                "passthrough",
                "samplefile",
        ):
            val = getattr(self, name, None)
            if val is not None:
                s.append(f"{name:>15.15s}: {val!s}")
        return "\n".join(s)
