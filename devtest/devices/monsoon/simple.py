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

import sys
import struct

from devtest import usb
from devtest.devices.monsoon import core


FLOAT_TO_INT = 1048576


class Monsoon:
    """Base class for type checking."""


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
        usbdev.configuration = 1
        try:
            usbdev.claim_interface(0)
        except usb.LibusbError:
            pass
        self._dev = usbdev
        if self.hardware_model != core.HardwareModel.HVPM:
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
                                          core.ControlCodes.USB_SET_VALUE, 0, opcode, 4)
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
                                   core.ControlCodes.USB_SET_VALUE, wValue, wIndex, buf)

    def reset(self):
        try:
            self.send_command(core.OpCodes.ResetPowerMonitor, 0)
        except usb.LibusbError:
            pass
        self.close()

    def calibrate_voltage(self):
        self.send_command(core.OpCodes.CalibrateMainVoltage, 0)

    @property
    def info(self):
        info = core.MonsoonInfo()
        info.populate(self)
        return info

    @property
    def hardware_model(self):
        return self.get_value(core.OpCodes.HardwareModel)

    @property
    def serial(self):
        return self.get_value(core.OpCodes.GetSerialNumber)

    @property
    def status(self):
        return self.get_value(core.OpCodes.GetStartStatus)

    @property
    def voltage(self):
        return self._voltage

    @voltage.setter
    def voltage(self, value):
        vout = int(value * FLOAT_TO_INT)
        self.send_command(core.OpCodes.SetMainVoltage, vout)
        self._voltage = value

    def disable_vout(self):
        self.send_command(core.OpCodes.SetMainVoltage, 0)

    def enable_vout(self):
        if self._voltage:
            self.send_command(core.OpCodes.SetMainVoltage, int(self._voltage * FLOAT_TO_INT))
        else:
            self._voltage = 1.5
            self.send_command(core.OpCodes.SetMainVoltage, int(self._voltage * FLOAT_TO_INT))

    @property
    def voltage_channel(self):
        val = self.get_value(core.OpCodes.SetVoltageChannel)
        return core.VoltageChannel(val)

    @voltage_channel.setter
    def voltage_channel(self, chan):
        self.send_command(core.OpCodes.SetVoltageChannel, int(chan))

    @property
    def usb_passthrough(self):
        return self.get_value(core.OpCodes.SetUSBPassthroughMode)

    @usb_passthrough.setter
    def usb_passthrough(self, value):
        self.send_command(core.OpCodes.SetUSBPassthroughMode, int(value))

    def is_sampling(self):
        status = self.get_value(core.OpCodes.GetStartStatus)
        return bool(status & 0x80)

    def start_sampling(self, samples, calsamples=1250):
        buf = struct.pack("<I", samples)
        self._dev.control_transfer(usb.RequestRecipient.Device,
                                   usb.RequestType.Vendor,
                                   usb.EndpointDirection.Out,
                                   core.ControlCodes.USB_REQUEST_START, calsamples, 0, buf)

    def stop_sampling(self):
        buf = b'\xff\xff\xff\xff'
        self._dev.control_transfer(usb.RequestRecipient.Device,
                                   usb.RequestType.Vendor,
                                   usb.EndpointDirection.Out,
                                   core.ControlCodes.USB_REQUEST_STOP, 0, 0, buf)

    def read_sample(self):
        return self._dev.bulk_transfer(1, usb.EndpointDirection.In, 64, timeout=1000)

    def capture(self, samples=None, duration=None, handler=None, calsamples=1250):
        """Perform a measurement series.

        Arguments:
            samples: An int, number of samples to take.
            duration: Number of seconds to run. Overrides samples, and one of
                      these two must be provided.
            handler: callabled that gets called for each sample, like so:
                     handler((main_coarse, main_fine, usb_coarse, usb_fine,
                             aux_coarse, aux_fine, main_voltage, usb_voltage,
                             main_coarse_gain, main_fine_gain, usb_gain,
                             sampletype))
                    This is, a single tuple of those items.
            calsamples: Time in milliseconds between calibration samples.
                        Default is 1250.
        """
        if samples is None and duration is None:
            raise ValueError("You must supply either number of samples or sampling duration.")
        if duration:
            samples = 5000 * int(duration)
        else:
            samples = int(samples)

        if handler is None:
            def handler(sample):
                print(repr(sample))

        headreader = struct.Struct("<HBB")
        datareader = struct.Struct(">HHHHHHHHBB")
        dropped_count = 0
        sample_count = 0
        try:
            self.start_sampling(samples, calsamples)
            while (sample_count + dropped_count) < samples:
                try:
                    data = self.read_sample()
                    dropped, flags, number = headreader.unpack(data[:headreader.size])
                    dropped_count = dropped  # device accumulates dropped sample count.
                    sample_count += number
                    for start, end in zip(
                            range(headreader.size,
                                  datareader.size * (number + 1),
                                  datareader.size),
                            range(datareader.size + headreader.size,
                                  datareader.size * (number + 1),
                                  datareader.size)):
                        (main_coarse, main_fine, usb_coarse, usb_fine,
                         aux_coarse, aux_fine, main_voltage, usb_voltage,
                         main_gain, flags) = datareader.unpack(data[start:end])
                        main_coarse_gain = (main_gain & 0xFF00) >> 8
                        main_fine_gain =  main_gain & 0xFF
                        # flags: usb sense D- (D7), usb sense D+ (D6); mode
                        # (D5…4) 0 is a measurement, 1 is zero calibration, 2 is
                        # a first sample (invalid), and 3 is a reference
                        # calibration, and finally usb gain (D3…0).
                        usb_gain = flags & 0X0F
                        sampletype = flags & 0x30
                        handler((main_coarse, main_fine, usb_coarse, usb_fine,
                                 aux_coarse, aux_fine, main_voltage, usb_voltage,
                                 main_coarse_gain, main_fine_gain, usb_gain,
                                 sampletype))
                except usb.LibusbError as e:
                    print(e, file=sys.stderr)
                    break
        finally:
            self.stop_sampling()
        return sample_count, dropped_count



def _test(argv):
    serial = argv[1] if len(argv) > 1 else None

    samples = 5000 * 5
    unpacker = struct.Struct("<HBB")
    dropped_count = 0
    sample_count = 0

    dev = HVPM()
    dev.open(serial)
    dev.voltage_channel = core.VoltageChannel.MainAndUSB
    dev.usb_passthrough = core.USBPassthrough.On

    if not dev.is_sampling():
        outf = open("samples.dat", "wb")

        dev.voltage = 4.2
        try:
            dev.start_sampling(samples)
            while (sample_count + dropped_count) < samples:
                try:
                    data = dev.read_sample()
                    dropped, flags, number = unpacker.unpack(data[:4])
                    dropped_count = dropped  # device accumulates dropped sample count.
                    sample_count += number
                    outf.write(data)
                except usb.LibusbError as e:
                    print(e)
                    break
        finally:
            dev.stop_sampling()
            outf.close()
        print("samples:", sample_count, "dropped:", dropped_count)
    else:
        print("Not ready!")
        dev.stop_sampling()
    dev.close()


if __name__ == "__main__":
    _test(sys.argv)
