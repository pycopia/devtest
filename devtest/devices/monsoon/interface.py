"""Monsoon interface using synchronous USB."""

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

import struct

from devtest import logging
from devtest import usb
from devtest.devices.monsoon import core

_VOLTAGE_SCALE = 1048576

# pylint: disable=too-few-public-methods,too-many-positional-arguments
# pylint: disable=too-many-locals


class StopSampling(Exception):
    """Used to signal a long-running capture to stop."""


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
        """Open a connection to a Monsoon by serial number."""
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
        """Close connection to this Monsoon."""
        if self._dev is not None:
            try:
                self._dev.release_interface(0)
            except usb.LibusbError:
                pass
            self._dev.close()
            self._dev = None
        self._sess = None

    def _get_raw_value(self, opcode):
        resp = self._dev.control_transfer(
            usb.RequestRecipient.Device,
            usb.RequestType.Vendor,
            usb.EndpointDirection.In,
            core.ControlCodes.USB_SET_VALUE,
            0,
            opcode,
            4,
        )
        return resp

    def get_value(self, code):
        """Get a config or setting value from device."""
        opcode, fmt = code.value
        raw = self._get_raw_value(opcode)
        return struct.unpack(fmt, raw[:struct.calcsize(fmt)])[0]

    def _send_command(self, code, value):
        opcode, _ = code.value
        buf = struct.pack("I", value)
        w_value = value & 0xFFFF
        w_index = (opcode & 0xFF) | ((value & 0xFF0000) >> 8)
        self._dev.control_transfer(
            usb.RequestRecipient.Device,
            usb.RequestType.Vendor,
            usb.EndpointDirection.Out,
            core.ControlCodes.USB_SET_VALUE,
            w_value,
            w_index,
            buf,
        )

    def reset(self):
        """Reset the power monitor."""
        try:
            self._send_command(core.OpCodes.ResetPowerMonitor, 0)
        except usb.LibusbError:
            pass
        self.close()

    def calibrate_voltage(self):
        """Send command to calibrate voltage."""
        self._send_command(core.OpCodes.CalibrateMainVoltage, 0)

    @property
    def info(self) -> core.MonsoonInfo:
        """Information about this Monsoon."""
        info = core.MonsoonInfo()
        info.populate(self)
        return info

    @property
    def hardware_model(self):
        """The hardware model."""
        return self.get_value(core.OpCodes.HardwareModel)

    @property
    def serial(self):
        """The serial number."""
        return self.get_value(core.OpCodes.GetSerialNumber)

    @property
    def status(self):
        """The current status."""
        return self.get_value(core.OpCodes.GetStartStatus)

    @property
    def voltage(self):
        """The configured voltage."""
        return self._voltage

    @voltage.setter
    def voltage(self, value):
        vout = int(value * _VOLTAGE_SCALE)
        self._send_command(core.OpCodes.SetMainVoltage, vout)
        self._voltage = value

    def disable_vout(self):
        """Turn output off."""
        self._send_command(core.OpCodes.SetMainVoltage, 0)

    def enable_vout(self):
        """Turn output on and set voltage."""
        if self._voltage:
            self._send_command(core.OpCodes.SetMainVoltage, int(self._voltage * _VOLTAGE_SCALE))
        else:
            self._voltage = 1.5
            self._send_command(core.OpCodes.SetMainVoltage, int(self._voltage * _VOLTAGE_SCALE))

    @property
    def voltage_channel(self) -> core.VoltageChannel:
        """The voltage channel."""
        val = self.get_value(core.OpCodes.SetVoltageChannel)
        return core.VoltageChannel(val)

    @voltage_channel.setter
    def voltage_channel(self, chan):
        self._send_command(core.OpCodes.SetVoltageChannel, int(chan))

    @property
    def usb_passthrough(self):
        """Current passthrough mode."""
        return self.get_value(core.OpCodes.SetUSBPassthroughMode)

    @usb_passthrough.setter
    def usb_passthrough(self, value):
        self._send_command(core.OpCodes.SetUSBPassthroughMode, int(value))

    def is_sampling(self):
        """True if currently sampling."""
        status = self.get_value(core.OpCodes.GetStartStatus)
        return bool(status & 0x80)

    def start_sampling(self, samples, calsamples=1250):
        """Start sampling and sending samples data."""
        buf = struct.pack("<I", samples)
        self._dev.control_transfer(
            usb.RequestRecipient.Device,
            usb.RequestType.Vendor,
            usb.EndpointDirection.Out,
            core.ControlCodes.USB_REQUEST_START,
            calsamples,
            0,
            buf,
        )

    def stop_sampling(self):
        """Stop sampling and sending sample data."""
        buf = b"\xff\xff\xff\xff"
        self._dev.control_transfer(
            usb.RequestRecipient.Device,
            usb.RequestType.Vendor,
            usb.EndpointDirection.Out,
            core.ControlCodes.USB_REQUEST_STOP,
            0,
            0,
            buf,
        )

    def _read_sample(self):
        return self._dev.bulk_transfer(1, usb.EndpointDirection.In, 64, timeout=1000)

    def capture(
        self,
        samples=None,
        duration=None,
        handler=None,
        calsamples=1250,
        startdelay=0,
    ):
        """Perform a measurement series.

    Arguments:
        samples: An int, number of measurement samples to take.
        duration: Number of seconds to run. Overrides samples, and one of these
          two must be provided.
        handler: callabled that gets called for each sample, like so:
          handler((main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse,
          aux_fine, main_voltage, usb_voltage, main_coarse_gain, main_fine_gain,
          usb_gain, sampletype)) This is, a single tuple of those items.
        calsamples: Time in milliseconds between calibration samples. Default is
          1250.
        startdelay: Time in seconds to wait before sending samples to handler.
          Allows for settle time of DUT. Default is zero. This does not effect
          duration time.
    """
        if samples is None and duration is None:
            raise ValueError("You must supply either number of samples or sampling duration.")
        if duration:
            samples = 5000 * int(duration)  # use samples as ticks
        else:
            samples = int(samples)
        startsample = 5000 * int(startdelay)
        total_samples = min(
            samples + startsample + int(((samples / 5000) / (calsamples / 1000.0)) * 12),
            4294967295,
        )

        if handler is None:

            def handler(sample):  # Used for self test
                print(repr(sample))

        decodehead = struct.Struct("<HBB")
        decodedata = struct.Struct(">HHHHHHHHBB")
        dropped_count = 0
        sample_count = 0
        try:
            self.start_sampling(total_samples, calsamples)
            while (sample_count + dropped_count) < total_samples:
                try:
                    data = self._read_sample()
                    dropped, flags, number = decodehead.unpack(data[:decodehead.size])
                    dropped_count = dropped  # device accumulates dropped sample count.
                    sample_count += number
                    if sample_count < startsample:
                        continue
                    for start, end in zip(
                            range(
                                decodehead.size,
                                decodedata.size * (number + 1),
                                decodedata.size,
                            ),
                            range(
                                decodedata.size + decodehead.size,
                                decodedata.size * (number + 1),
                                decodedata.size,
                            ),
                    ):
                        (
                            main_coarse,
                            main_fine,
                            usb_coarse,
                            usb_fine,
                            aux_coarse,
                            aux_fine,
                            main_voltage,
                            usb_voltage,
                            main_gain,
                            flags,
                        ) = decodedata.unpack(data[start:end])
                        main_coarse_gain = (main_gain & 0xFF00) >> 8
                        main_fine_gain = main_gain & 0xFF
                        # flags: usb sense D- (D7), usb sense D+ (D6); mode
                        # (D5…4) 0 is a measurement, 1 is zero calibration, 2 is
                        # a first sample (invalid), and 3 is a reference
                        # calibration, and finally usb gain (D3…0).
                        usb_gain = flags & 0x0F
                        sampletype = flags & 0x30
                        handler((
                            main_coarse,
                            main_fine,
                            usb_coarse,
                            usb_fine,
                            aux_coarse,
                            aux_fine,
                            main_voltage,
                            usb_voltage,
                            main_coarse_gain,
                            main_fine_gain,
                            usb_gain,
                            sampletype,
                        ))
                except usb.LibusbError as e:
                    logging.exception_error("USB error while sampling", e)
                    break
                except StopSampling:
                    break
        finally:
            self.stop_sampling()
        return sample_count, dropped_count
