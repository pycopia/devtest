# python3

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


class PowerMeterRole(BaseRole):
    """Provide power meter role controller.

    This one uses Monsoon device.
    """

    def measure_average_power(self, duration=10, samples=None, voltage=4.2,
                              passthrough="auto", delay=0):
        """Measure and report average power over the span of time.
        """
        measure_context = {
            "serialno": self._equipment["serno"],
            "passthrough": passthrough,
            "voltage": float(voltage),
            "numsamples": samples,
            "duration": int(duration),
            "delay": int(delay),
        }
        measurer = measure.MonsoonCurrentMeasurer(measure_context)
        result = measurer.measure(handlerclass=measure.AveragePowerHandler)
        return result.main_power, result.usb_power

    def record(self, filename, duration=10, samples=None, voltage=4.2,
               passthrough="auto", delay=0):
        """Record all samples to a file.
        """
        measure_context = {
            "serialno": self._equipment["serno"],
            "passthrough": passthrough,
            "voltage": float(voltage),
            "numsamples": samples,
            "duration": int(duration),
            "delay": int(delay),
            "filename": filename,
        }
        measurer = measure.MonsoonCurrentMeasurer(measure_context)
        result = measurer.measure(handlerclass=measure.FileHandler)
        return result


if __name__ == "__main__":
    device = {
            "serno": "20418",
    }
    dev = PowerMeterRole(device)
    main_power, usb_power = dev.measure_average_power(passthrough="on")
    print("Main power: {:10.4f} W, USB power: {:10.4f} W".format(main_power, usb_power))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
