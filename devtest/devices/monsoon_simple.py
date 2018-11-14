#!/usr/bin/python3.6

"""Simple Monsoon interface using synchronous USB.
"""

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

    def __init__(self):
        self._dev = None

    def __del__(self):
        self.close()

    def open(self, serial):
        sess = usb.UsbSession()
        usbdev = sess.find(HVPM.VID, HVPM.PID, serial=serial)
        if not usbdev:
            raise ValueError("No device with that serial found.")
        usbdev.open()
        usbdev.configuration = 0
        self._dev = usbdev
        if self.hardware_model != HardwareModel.HVPM:
            self.close()
            raise ValueError("Didn't get right model for this controller.")

    def close(self):
        if self._dev is not None:
            self._dev.close()
            self._dev = None

    def get_raw_value(self, opcode):
        resp = self._dev.control_transfer(usb.RequestRecipient.Device,
                                          usb.RequestType.Vendor,
                                          usb.EndpointDirection.In,
                                          ControlCodes.USB_SET_VALUE, 0, opcode, 4)
        return resp

    def get_value(self, code):
        opcode, fmt = code.value
        raw = self.get_raw_value(opcode)
        return struct.unpack(fmt, raw[:struct.calcsize(fmt)])[0]

    @property
    def hardware_model(self):
        return self.get_value(OpCodes.HardwareModel)

    @property
    def serial(self):
        return self.get_value(OpCodes.GetSerialNumber)

    @property
    def status(self):
        return self.get_value(OpCodes.getStartStatus)


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
    SetUsbCoarseResistorOffset = (0x12, "B")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBCoarseScale = (0x1D, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBCoarseZeroOffset = (0x28, "h")  # Zero-level offset
    SetUsbFineResistorOffset = (0x0D, "b")  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    SetUSBFineScale = (0x1C, "H")  # HVPM Calibration value, 32-bits, unsigned
    SetUSBFineZeroOffset = (0x27, "h")  # Zero-level offset
    SetUsbPassthroughMode = (0x10, "B")  # Sets USB Passthrough mode according to value.  Off = 0, On = 1, Auto = 2
    SetVoltageChannel = (0x23, None)  # Sets voltage channel:  Value 00 = Main & USB voltage measurements.  Value 01 = Main & Aux voltage measurements
    Stop = (0xFF, None)


class HardwareModel(enum.IntEnum):
    UNKNOWN = 0
    LVPM = 1
    HVPM = 2


class ControlCodes(enum.IntEnum):
    USB_REQUEST_START = 0x02
    USB_REQUEST_STOP = 0x03
    USB_SET_VALUE = 0x01
    USB_REQUEST_RESET_TO_BOOTLOADER = 0xFF


class USBPassthrough(enum.IntEnum):
    """Values for setting or retrieving the USB Passthrough mode."""
    Off = 0
    On = 1
    Auto = 2


class VoltageChannel(enum.IntEnum):
    """Values for setting or retrieving the Voltage Channel."""
    Main = 0
    USB = 1
    Aux = 2


class MonsoonInfo:
    """Values stored in the Power Monitor EEPROM.  Each corresponds to an opcode"""
    FirmwareVersion = 0  # Firmware version number.
    ProtocolVersion = 0  # Protocol version number.
    Temperature = 0  # Current temperature reading from the board.
    SerialNumber = 0  # Unit's serial number.
    PowerupCurrentLimit = 0   # Max current during startup before overcurrent protection circuit activates.  LVPM is 0-8A, HVPM is 0-15A.
    RuntimeCurrentLimit = 0  # Max current during runtime before overcurrent protection circuit activates.  LVPM is 0-8A, HVPM is 0-15A.
    PowerupTime = 0  # Time in ms the powerupcurrent limit will be used.
    TemperatureLimit = 0  # Temperature limit in Signed Q7.8 format
    UsbPassthroughMode = 0  #  Off = 0, On = 1, Auto = 2

    MainFineScale = 0  # HVPM Calibration value, 32-bits, unsigned
    MainCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned
    UsbFineScale = 0 # HVPM Calibration value, 32-bits, unsigned
    UsbCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned
    AuxFineScale = 0 # HVPM Calibration value, 32-bits, unsigned
    AuxCoarseScale = 0 # HVPM Calibration value, 32-bits, unsigned

    MainFineZeroOffset = 0  # HVPM-only, Zero-level offset
    MainCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    UsbFineZeroOffset = 0  # HVPM-only, Zero-level offset
    UsbCoarseZeroOffset = 0  # HVPM-only, Zero-level offset
    HardwareModel = 0  # HVPM-only, Zero-level offset

    MainFineResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    MainCoarseResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    UsbFineResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    UsbCoarseResistorOffset = 0  # signed, ohms = 0.05 + 0.0001*offset
    AuxFineResistorOffset = 0  # signed, ohms = 0.10 + 0.0001*offset
    AuxCoarseResistorOffset = 0  # signed, ohms = 0.10 + 0.0001*offset

    DacCalLow = 0
    DacCalHigh = 0

    def populate(self, dev):
        self.AuxCoarseResistorOffset = float(dev.get_value(OpCodes.SetAuxCoarseResistorOffset))
        self.AuxCoarseScale = float(dev.get_value(OpCodes.SetAuxCoarseScale))
        self.AuxFineResistorOffset = float(dev.get_value(OpCodes.SetAuxFineResistorOffset))
        self.AuxFineScale = float(dev.get_value(OpCodes.SetAuxFineScale))
        self.DacCalHigh = dev.get_value(OpCodes.DacCalHigh)
        self.DacCalLow = dev.get_value(OpCodes.DacCalLow)
        self.FirmwareVersion = dev.get_value(OpCodes.FirmwareVersion)
        self.HardwareModel = dev.get_value(OpCodes.HardwareModel)
        self.MainCoarseResistorOffset = float(dev.get_value(OpCodes.SetMainCoarseResistorOffset))
        self.MainCoarseScale = float(dev.get_value(OpCodes.SetMainCoarseScale))
        self.MainCoarseZeroOffset = float(dev.get_value(OpCodes.SetMainCoarseZeroOffset))
        self.MainFineResistorOffset = float(dev.get_value(OpCodes.SetMainFineResistorOffset))
        self.MainFineScale = float(dev.get_value(OpCodes.SetMainFineScale))
        self.MainFineZeroOffset = float(dev.get_value(OpCodes.SetMainFineZeroOffset))
        self.PowerupCurrentLimit = self.amps_from_raw(dev.get_value(OpCodes.SetPowerUpCurrentLimit))
        self.PowerupTime = dev.get_value(OpCodes.SetPowerupTime)
        self.ProtocolVersion = dev.get_value(OpCodes.ProtocolVersion)
        self.RuntimeCurrentLimit = self.amps_from_raw(dev.get_value(OpCodes.SetRunCurrentLimit))
        self.TemperatureLimit = self.degrees_from_raw(dev.get_value(OpCodes.SetTemperatureLimit))
        self.UsbCoarseResistorOffset = float(dev.get_value(OpCodes.SetUsbCoarseResistorOffset))
        self.UsbCoarseScale = float(dev.get_value(OpCodes.SetUSBCoarseScale))
        self.UsbCoarseZeroOffset = float(dev.get_value(OpCodes.SetUSBCoarseZeroOffset))
        self.UsbFineResistorOffset = float(dev.get_value(OpCodes.SetUsbFineResistorOffset))
        self.UsbFineScale = float(dev.get_value(OpCodes.SetUSBFineScale))
        self.UsbFineZeroOffset = float(dev.get_value(OpCodes.SetUSBFineZeroOffset))
        self.UsbPassthroughMode = dev.get_value(OpCodes.SetUsbPassthroughMode)

    def amps_from_raw(self, raw):
        offset = 3840.0 # == 0x0F00
        scale = float((raw - offset) / (65535.0 - offset))
        return 15.625 * scale

    def raw_from_amps(self, value):
        return (65535 - 0x0F00) * (value / 15.625) + 0x0F00

    def degrees_from_raw(self, value):
        """For setting the fan temperature limit.  Only valid in HVPM"""
        bytes_ = struct.unpack("BB", struct.pack("H", value)) #Firmware swizzles these bytes_.
        return bytes_[1] + (bytes_[0] * 2**-8)

    def __str__(self):
        s = []
        s.append("FirmwareVersion: {}".format(self.FirmwareVersion))
        s.append("ProtocolVersion: {}".format(self.ProtocolVersion))
        s.append("Temperature: {}".format(self.Temperature))
        s.append("SerialNumber: {}".format(self.SerialNumber))
        s.append("PowerupCurrentLimit: {}".format(self.PowerupCurrentLimit))
        s.append("RuntimeCurrentLimit: {}".format(self.RuntimeCurrentLimit))
        s.append("PowerupTime: {}".format(self.PowerupTime))
        s.append("TemperatureLimit: {}".format(self.TemperatureLimit))
        s.append("UsbPassthroughMode: {}".format(self.UsbPassthroughMode))
        s.append("MainFineScale: {}".format(self.MainFineScale))
        s.append("MainCoarseScale: {}".format(self.MainCoarseScale))
        s.append("UsbFineScale: {}".format(self.UsbFineScale))
        s.append("UsbCoarseScale: {}".format(self.UsbCoarseScale))
        s.append("AuxFineScale: {}".format(self.AuxFineScale))
        s.append("AuxCoarseScale: {}".format(self.AuxCoarseScale))
        s.append("MainFineZeroOffset: {}".format(self.MainFineZeroOffset))
        s.append("MainCoarseZeroOffset: {}".format(self.MainCoarseZeroOffset))
        s.append("UsbFineZeroOffset: {}".format(self.UsbFineZeroOffset))
        s.append("UsbCoarseZeroOffset: {}".format(self.UsbCoarseZeroOffset))
        s.append("HardwareModel: {}".format(self.HardwareModel))
        s.append("MainFineResistorOffset: {}".format(self.MainFineResistorOffset))
        s.append("MainCoarseResistorOffset: {}".format(self.MainCoarseResistorOffset))
        s.append("UsbFineResistorOffset: {}".format(self.UsbFineResistorOffset))
        s.append("UsbCoarseResistorOffset: {}".format(self.UsbCoarseResistorOffset))
        s.append("AuxFineResistorOffset: {}".format(self.AuxFineResistorOffset))
        s.append("AuxCoarseResistorOffset: {}".format(self.AuxCoarseResistorOffset))
        s.append("DacCalLow: {}".format(self.DacCalLow))
        s.append("DacCalHigh: {}".format(self.DacCalHigh))
        return "\n".join(s)


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
    serial = argv[1] if len(argv) > 1 else "20420"
    dev = HVPM()
    dev.open(serial)
    info = MonsoonInfo()
    info.populate(dev)
    print(info)
    dev.close()


if __name__ == "__main__":
    import sys
    _test(sys.argv)

