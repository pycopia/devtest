#!/usr/bin/python3.6

"""Simple Monsoon interface using synchronous USB.
"""

# Portions of this code were copied from the Monsoon open-source Python
# interface. It has the following license.

# Copyright 2017 Monsoon Solutions, Inc
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
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

import enum
import struct

from devtest import usb


FLOAT_TO_INT = 1048576


class Monsoon:
    pass


class HVPM(Monsoon):
    """A Monsoon HVPM Power Monitor."""
    VID = 0x2AB9
    PID = 0x0001
    # read-only instance attributes
    main_voltage_scale = property(lambda s: 4)
    usb_voltage_scale = property(lambda s: 2)
    ADCRatio = property(lambda s: 62.5 / 1e6)  # Each tick of the ADC represents this much voltage

    def __init__(self):
        self._dev = None
        self._sess = None
        self._voltage = None
        self.fine_threshold = 64000
        self.aux_fine_threshold = 30000

    def __del__(self):
        self.close()

    def open(self, serial):
        self._sess = usb.UsbSession()
        usbdev = self._sess.find(HVPM.VID, HVPM.PID, serial=serial)
        if not usbdev:
            raise usb.UsbUsageError("No device with that serial found.")
        usbdev.open()
        usbdev.set_auto_detach_kernel_driver(True)
        usbdev.configuration = 0
        try:
            usbdev.claim_interface(0)
        except usb.LibusbError:
            pass
        self._dev = usbdev
        if self.hardware_model != HardwareModel.HVPM:
            self.close()
            raise usb.UsbUsageError("Didn't get right model for this controller.")

    def close(self):
        if self._dev is not None:
            try:
                self._dev.release_interface(0)
            except usb.LibusbError:
                pass
            self._dev.close()
            self._dev = None
        self._sess = None

    def _get_raw_value(self, opcode):
        resp = self._dev.control_transfer(usb.RequestRecipient.Device,
                                          usb.RequestType.Vendor,
                                          usb.EndpointDirection.In,
                                          ControlCodes.USB_SET_VALUE, 0, opcode, 4)
        return resp

    def get_value(self, code):
        opcode, fmt = code.value
        raw = self._get_raw_value(opcode)
        return struct.unpack(fmt, raw[:struct.calcsize(fmt)])[0]

    def send_command(self, code, value):
        opcode, _ = code.value
        buf = struct.pack("I", value)
        wValue = value & 0xFFFF
        wIndex = (opcode & 0xFF) | ((value & 0xFF0000) >> 8)
        self._dev.control_transfer(usb.RequestRecipient.Device,
                                   usb.RequestType.Vendor,
                                   usb.EndpointDirection.Out,
                                   ControlCodes.USB_SET_VALUE, wValue, wIndex, buf)

    def reset(self):
        try:
            self.send_command(OpCodes.ResetPowerMonitor, 0)
        except usb.LibusbError:
            pass
        self.close()

    def calibrate_voltage(self):
        self.send_command(OpCodes.CalibrateMainVoltage, 0)

    @property
    def info(self):
        info = MonsoonInfo()
        info.populate(self)
        return info

    @property
    def hardware_model(self):
        return self.get_value(OpCodes.HardwareModel)

    @property
    def serial(self):
        return self.get_value(OpCodes.GetSerialNumber)

    @property
    def status(self):
        return self.get_value(OpCodes.GetStartStatus)

    @property
    def voltage(self):
        return self._voltage

    @voltage.setter
    def voltage(self, value):
        vout = int(value * FLOAT_TO_INT)
        self.send_command(OpCodes.SetMainVoltage, vout)
        self._voltage = value

    def disable_vout(self):
        self.send_command(OpCodes.SetMainVoltage, 0)

    def enable_vout(self):
        if self._voltage:
            self.send_command(OpCodes.SetMainVoltage, int(self._voltage * FLOAT_TO_INT))
        else:
            self._voltage = 1.5
            self.send_command(OpCodes.SetMainVoltage, int(self._voltage * FLOAT_TO_INT))

    @property
    def voltage_channel(self):
        val = self.get_value(OpCodes.SetVoltageChannel)
        return VoltageChannel(val)

    @voltage_channel.setter
    def voltage_channel(self, chan):
        self.send_command(OpCodes.SetVoltageChannel, int(chan))

    @property
    def usb_passthrough(self):
        return self.get_value(OpCodes.SetUSBPassthroughMode)

    @usb_passthrough.setter
    def usb_passthrough(self, value):
        self.send_command(OpCodes.SetUSBPassthroughMode, int(value))

    def is_sampling(self):
        status = self.get_value(OpCodes.GetStartStatus)
        return bool(status & 0x80)

    def start_sampling(self, caltime, maxtime):
        buf = struct.pack("<I", maxtime)
        self._dev.control_transfer(usb.RequestRecipient.Device,
                                   usb.RequestType.Vendor,
                                   usb.EndpointDirection.Out,
                                   ControlCodes.USB_REQUEST_START, caltime, 0, buf)

    def stop_sampling(self):
        buf = b'\xff\xff\xff\xff'
        self._dev.control_transfer(usb.RequestRecipient.Device,
                                   usb.RequestType.Vendor,
                                   usb.EndpointDirection.Out,
                                   ControlCodes.USB_REQUEST_STOP, 0, 0, buf)

    def read_sample(self):
        resp = self._dev.bulk_transfer(1, usb.EndpointDirection.In, 64, timeout=1000)
        return resp


class HardwareModel(enum.IntEnum):
    UNKNOWN = 0
    LVPM = 1
    HVPM = 2


class USBPassthrough(enum.IntEnum):
    """Values for setting or retrieving the USB Passthrough mode."""
    Off = 0
    On = 1
    Auto = 2


class OpCodes(enum.Enum):
    """USB Control Transfer operation codes: (code, struct_format)"""
    CalibrateMainVoltage = (0x03, None)  # Internal voltage calibration, affects accuracy of setHVMainVoltage
    DacCalHigh = (0x89, "H")  # 4.096V ADC Reference Calibration
    DacCalLow = (0x88, "H")  # 2.5V ADC Reference Calibration
    FirmwareVersion = (0xC0, "H")  # Read-only, gets the firmware version
    GetSerialNumber = (0x42, "I")
    GetStartStatus = (0xC4, "B")
    HardwareModel = (0x45, "H")  # 0 = unknown, 1 = LV, 2 = HV
    ProtocolVersion = (0xC1, "B")  # Read-only, gets the Protocol version
    ResetPowerMonitor = (0x05, None)  # Reset the PIC.  Causes disconnect.
    SetAuxCoarseResistorOffset = (0x13, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    SetAuxCoarseScale = (0x1F, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetAuxFineResistorOffset = (0x0E, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    SetAuxFineScale = (0x1E, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetMainCoarseResistorOffset = (0x11, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetMainCoarseScale = (0x1B, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetMainCoarseZeroOffset = (0x26, "h")  # Zero-level offset
    SetMainFineResistorOffset = (0x02, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetMainFineScale = (0x1A, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetMainFineZeroOffset = (0x25, "h")  # Zero-level offset
    SetMainVoltage = (0x41, None)  #  Voltage = value * 1048576
    SetPowerUpCurrentLimit = (0x43, "H")  # Sets power-up current limit.  HV Amps = 15.625*(1.0-powerupCurrentLimit/65535) #LV amps = 8.0*(1.0-powerupCurrentLimit/1023.0)
    SetPowerupTime = (0x0C, "B")  # time in milliseconds that the powerup current limit is in effect.
    SetRunCurrentLimit = (0x44, "H")  # Sets runtime current limit        HV Amps = 15.625*(1.0-powerupCurrentLimit/65535) #LV amps = 8.0*(1.0-powerupCurrentLimit/1023.0)
    SetTemperatureLimit = (0x29, "H")  # Temperature limit in Signed Q7.8 format
    SetUSBCoarseResistorOffset = (0x12, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBCoarseScale = (0x1D, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBCoarseZeroOffset = (0x28, "h")  # Zero-level offset
    SetUSBFineResistorOffset = (0x0D, "b")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBFineScale = (0x1C, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBFineZeroOffset = (0x27, "h")  # Zero-level offset
    SetUSBPassthroughMode = (0x10, "B")  # Sets USB Passthrough mode according to value.  Off = 0, On = 1, Auto = 2
    SetVoltageChannel = (0x23, "B")  # Sets voltage channel:  Value 00 = Main & USB voltage measurements.  Value 01 = Main & Aux voltage measurements
    Stop = (0xFF, None)


class VoltageChannel(enum.IntEnum):
    """Values for setting or retrieving the Voltage Channel."""
    MainAndUSB = 0
    MainAndAux = 1


class ControlCodes(enum.IntEnum):
    USB_REQUEST_START = 0x02
    USB_REQUEST_STOP = 0x03
    USB_SET_VALUE = 0x01
    USB_REQUEST_RESET_TO_BOOTLOADER = 0xFF


class MonsoonInfo:
    """Values stored in the Power Monitor EEPROM.  Each corresponds to an opcode.
    """
    AuxCoarseResistorOffset = 0  # signed, ohms = 0.10 + 0.0001*offset
    AuxCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned
    AuxFineResistorOffset = 0  # signed, ohms = 0.10 + 0.0001*offset
    AuxFineScale = 0 # HVPM Calibration value, 32-bits, unsigned
    DacCalHigh = 0
    DacCalLow = 0
    FirmwareVersion = 0  # Firmware version number.
    HardwareModel = HardwareModel(0)
    MainCoarseResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    MainCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned
    MainCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    MainFineResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    MainFineScale = 0  # HVPM Calibration value, 32-bits, unsigned
    MainFineZeroOffset = 0  # HVPM-only, Zero-level offset
    PowerupCurrentLimit = 0   # Max current during startup before overcurrent protection circuit activates.  LVPM is 0-8A, HVPM is 0-15A.
    PowerupTime = 0  # Time in ms the powerupcurrent limit will be used.
    ProtocolVersion = 0  # Protocol version number.
    RuntimeCurrentLimit = 0  # Max current during runtime before overcurrent protection circuit activates.  LVPM is 0-8A, HVPM is 0-15A.
    SerialNumber = 0  # Unit's serial number.
    TemperatureLimit = 0  # Temperature limit in Signed Q7.8 format
    UsbCoarseResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    UsbCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned
    UsbCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    UsbFineResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    UsbFineScale = 0 # HVPM Calibration value, 32-bits, unsigned
    UsbFineZeroOffset = 0  # HVPM-only, Zero-level offset
    UsbPassthroughMode = USBPassthrough(0)  #  Off = 0, On = 1, Auto = 2
    VoltageChannel = VoltageChannel(0)

    def populate(self, dev):
        self.SerialNumber = dev.serial
        self.AuxCoarseResistorOffset = float(dev.get_value(OpCodes.SetAuxCoarseResistorOffset))
        self.AuxCoarseScale = float(dev.get_value(OpCodes.SetAuxCoarseScale))
        self.AuxFineResistorOffset = float(dev.get_value(OpCodes.SetAuxFineResistorOffset))
        self.AuxFineScale = float(dev.get_value(OpCodes.SetAuxFineScale))
        self.DacCalHigh = dev.get_value(OpCodes.DacCalHigh)
        self.DacCalLow = dev.get_value(OpCodes.DacCalLow)
        self.FirmwareVersion = dev.get_value(OpCodes.FirmwareVersion)
        self.HardwareModel = HardwareModel(dev.get_value(OpCodes.HardwareModel))
        self.MainCoarseResistorOffset = float(dev.get_value(OpCodes.SetMainCoarseResistorOffset))
        self.MainCoarseScale = float(dev.get_value(OpCodes.SetMainCoarseScale))
        self.MainCoarseZeroOffset = float(dev.get_value(OpCodes.SetMainCoarseZeroOffset))
        self.MainFineResistorOffset = float(dev.get_value(OpCodes.SetMainFineResistorOffset))
        self.MainFineScale = float(dev.get_value(OpCodes.SetMainFineScale))
        self.MainFineZeroOffset = float(dev.get_value(OpCodes.SetMainFineZeroOffset))
        self.PowerupCurrentLimit = _amps_from_raw(dev.get_value(OpCodes.SetPowerUpCurrentLimit))
        self.PowerupTime = dev.get_value(OpCodes.SetPowerupTime)
        self.ProtocolVersion = dev.get_value(OpCodes.ProtocolVersion)
        self.RuntimeCurrentLimit = _amps_from_raw(dev.get_value(OpCodes.SetRunCurrentLimit))
        self.TemperatureLimit = _degrees_from_raw(dev.get_value(OpCodes.SetTemperatureLimit))
        self.UsbCoarseResistorOffset = float(dev.get_value(OpCodes.SetUSBCoarseResistorOffset))
        self.UsbCoarseScale = float(dev.get_value(OpCodes.SetUSBCoarseScale))
        self.UsbCoarseZeroOffset = float(dev.get_value(OpCodes.SetUSBCoarseZeroOffset))
        self.UsbFineResistorOffset = float(dev.get_value(OpCodes.SetUSBFineResistorOffset))
        self.UsbFineScale = float(dev.get_value(OpCodes.SetUSBFineScale))
        self.UsbFineZeroOffset = float(dev.get_value(OpCodes.SetUSBFineZeroOffset))
        self.UsbPassthroughMode = USBPassthrough(dev.get_value(OpCodes.SetUSBPassthroughMode))
        self.VoltageChannel = VoltageChannel(dev.get_value(OpCodes.SetVoltageChannel))

    def __str__(self):
        s = []
        s.append("SerialNumber: {}".format(self.SerialNumber))
        s.append("AuxCoarseResistorOffset: {}".format(self.AuxCoarseResistorOffset))
        s.append("AuxCoarseScale: {}".format(self.AuxCoarseScale))
        s.append("AuxFineResistorOffset: {}".format(self.AuxFineResistorOffset))
        s.append("AuxFineScale: {}".format(self.AuxFineScale))
        s.append("DacCalHigh: {}".format(self.DacCalHigh))
        s.append("DacCalLow: {}".format(self.DacCalLow))
        s.append("FirmwareVersion: {}".format(self.FirmwareVersion))
        s.append("HardwareModel: {!r}".format(self.HardwareModel))
        s.append("MainCoarseResistorOffset: {}".format(self.MainCoarseResistorOffset))
        s.append("MainCoarseScale: {}".format(self.MainCoarseScale))
        s.append("MainCoarseZeroOffset: {}".format(self.MainCoarseZeroOffset))
        s.append("MainFineResistorOffset: {}".format(self.MainFineResistorOffset))
        s.append("MainFineScale: {}".format(self.MainFineScale))
        s.append("MainFineZeroOffset: {}".format(self.MainFineZeroOffset))
        s.append("PowerupCurrentLimit: {}".format(self.PowerupCurrentLimit))
        s.append("PowerupTime: {}".format(self.PowerupTime))
        s.append("ProtocolVersion: {}".format(self.ProtocolVersion))
        s.append("RuntimeCurrentLimit: {}".format(self.RuntimeCurrentLimit))
        s.append("TemperatureLimit: {}".format(self.TemperatureLimit))
        s.append("UsbCoarseResistorOffset: {}".format(self.UsbCoarseResistorOffset))
        s.append("UsbCoarseScale: {}".format(self.UsbCoarseScale))
        s.append("UsbCoarseZeroOffset: {}".format(self.UsbCoarseZeroOffset))
        s.append("UsbFineResistorOffset: {}".format(self.UsbFineResistorOffset))
        s.append("UsbFineScale: {}".format(self.UsbFineScale))
        s.append("UsbFineZeroOffset: {}".format(self.UsbFineZeroOffset))
        s.append("UsbPassthroughMode: {!r}".format(self.UsbPassthroughMode))
        s.append("VoltageChannel: {!r}".format(self.VoltageChannel))
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
    EEPROM = 0xf0


class SampleType(enum.IntEnum):
    """Corresponds to the sampletype field from a sample packet."""
    Measurement = 0x00
    ZeroCal = 0x10
    invalid = 0x20
    refCal = 0x30


def _test(argv):
    from devtest import timers
    serial = argv[1] if len(argv) > 1 else "20420"
    dev = HVPM()
    dev.open(serial)
    print(dev.info)

    dev.voltage_channel = VoltageChannel.MainAndUSB
    dev.usb_passthrough = USBPassthrough.On

    if not dev.is_sampling():
        dev.voltage = 4.2
        timers.nanosleep(0.2)
        try:
            dev.start_sampling(1250, 5000 * 5)
            timers.nanosleep(0.002)
            for i in range(5000 * 5):
                print(repr(dev.read_sample()))
                timers.nanosleep(0.000002)
        finally:
            dev.stop_sampling()
    else:
        print("Not ready!")
        dev.stop_sampling()
    dev.close()


if __name__ == "__main__":
    import sys
    _test(sys.argv)

