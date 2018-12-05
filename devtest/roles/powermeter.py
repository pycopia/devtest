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

"""The power measuring role.
"""

from devtest.devices.monsoon import measure

from . import BaseRole


class AveragePowerHandler(measure.MeasurementHandler):

    def initialize(self, context):
        self.main_current = self.usb_current = self.aux_current = self.main_voltage = self.usb_voltage = 0.  # noqa
        self.usb_power = 0.

    def __call__(self, sample):
        main_current, usb_current, aux_current, main_voltage, usb_voltage = self._process_raw(sample)  # noqa
        if main_current is not None:  # actual sample
            self.main_current = (main_current + ((self.measure_count - 1) * self.main_current) ) / self.measure_count
            self.main_voltage = (main_voltage + ((self.measure_count - 1) * self.main_voltage) ) / self.measure_count
            self.usb_current = (usb_current + ((self.measure_count - 1) * self.usb_current) ) / self.measure_count
            self.usb_voltage = (usb_voltage + ((self.measure_count - 1) * self.usb_voltage) ) / self.measure_count

    def finalize(self, counted, dropped):
        super().finalize(counted, dropped)
        self.main_power = self.main_voltage * (self.main_current / 1000.)
        self.usb_power = self.usb_voltage * (self.usb_current / 1000.)


class PowerMeterRole(BaseRole):
    """Provide power meter role controller.

    This one uses Monsoon device.
    """

    def measure_average_power(self, duration=10, samples=None, voltage=4.2,
                              passthrough="auto"):
        measure_context = {
            "serialno": self._equipment["serno"],
            "passthrough": passthrough,
            "voltage": float(voltage),
            "numsamples": samples,
            "duration": duration,
        }
        measurer = measure.MonsoonCurrentMeasurer(measure_context)
        result = measurer.measure(handlerclass=AveragePowerHandler)
        return result.main_power, result.usb_power


if __name__ == "__main__":
    device = {
            "serno": "20418",
    }
    dev = PowerMeterRole(device)
    main_power, usb_power = dev.measure_average_power(passthrough="on")
    print("Main power: {:10.4f} W, USB power: {:10.4f} W".format(main_power, usb_power))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
