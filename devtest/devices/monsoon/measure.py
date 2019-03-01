# python3.6

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capture and calibrate Monsoon measurements. Different actions may be taken
with different measurement handlers.
"""

import time
import struct
import collections

from devtest.devices.monsoon import simple as monsoon_simple
from devtest.devices.monsoon import core


class CalibrationData:
    def __init__(self, size=5):
        self.size = size
        self.clear()

    def clear(self):
        size = self.size
        init = [0] * size
        self._ref_fine = collections.deque(init, size)
        self._ref_coarse = collections.deque(init, size)
        self._zero_fine = collections.deque(init, size)
        self._zero_coarse = collections.deque(init, size)

    @property
    def is_calibrated(self):
        return ((0 not in self._ref_fine) and (0 not in self._ref_coarse) and
                (0 not in self._zero_fine) and (0 not in self._zero_coarse))

    def add_refcal_coarse(self, value):
        self._ref_coarse.appendleft(value)

    def add_refcal_fine(self, value):
        self._ref_fine.appendleft(value)

    def add_zerocal_coarse(self, value):
        self._zero_coarse.appendleft(value)

    def add_zerocal_fine(self, value):
        self._zero_fine.appendleft(value)

    @property
    def ref_coarse(self):
        return sum(self._ref_coarse) / self.size

    @property
    def ref_fine(self):
        return sum(self._ref_fine) / self.size

    @property
    def zero_coarse(self):
        return sum(self._zero_coarse) / self.size

    @property
    def zero_fine(self):
        return sum(self._zero_fine) / self.size


class MeasurementHandler:
    """Handlers are callable instances that do something with capture samples.
    """
    # All use these column names and units.
    COLUMNS = ("main_current", "usb_current", "aux_current", "main_voltage", "usb_voltage")
    UNITS = ("mA", "mA", "unknown", "V", "V")

    def __init__(self, context, metadata, calsize=5):
        self.metadata = metadata
        self.sample_count = 0
        self.sample_rate = 5000  # fixed samples/sec
        self.cal_count = 0
        self.captured = 0
        self.dropped = 0
        self.measure_count = 0
        self.zerocal_count = 0
        self.refcal_count = 0
        self.invalid_count = 0
        self._main_cal = CalibrationData(calsize)
        self._usb_cal = CalibrationData(calsize)
        self._aux_cal = CalibrationData(calsize)
        self.initialize(context)

    @property
    def is_calibrated(self):
        return (self._main_cal.is_calibrated and self._usb_cal.is_calibrated and
                self._aux_cal.is_calibrated)

    def initialize(self, context):
        pass

    def finalize(self, captured, dropped):
        self.captured = captured
        self.dropped = dropped

    def __call__(self, sample):
        pass

    def __str__(self):
        s = ["Reported: captured: {}, dropped: {}".format(self.captured, self.dropped)]
        s.append("Counted:")
        s.append("  samples: {}".format(self.sample_count))
        s.append("  measure: {}".format(self.measure_count))
        s.append("  zerocal: {}".format(self.zerocal_count))
        s.append("   refcal: {}".format(self.refcal_count))
        s.append("  invalid: {}".format(self.invalid_count))
        return "\n".join(s)

    def _process_raw(self, sample):
        SampleType = core.SampleType
        self.sample_count += 1
        (main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse, aux_fine,
         main_voltage, usb_voltage, main_coarse_gain, main_fine_gain, usb_gain,
         sampletype) = sample
        if sampletype == SampleType.Measurement:
            if self.is_calibrated:
                self.measure_count += 1
                # Main Coarse
                zero_offset = self.metadata.MainCoarseZeroOffset
                cal_ref = self._main_cal.ref_coarse
                zero_offset += self._main_cal.zero_coarse
                try:
                    slope = self.metadata.MainCoarseScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                main_coarse_current = (main_coarse - zero_offset) * slope
                # Main Fine
                zero_offset = self.metadata.MainFineZeroOffset
                cal_ref = self._main_cal.ref_fine
                zero_offset += self._main_cal.zero_fine
                try:
                    slope = self.metadata.MainFineScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                main_fine_current = (main_fine - zero_offset) * slope / 1000.
                main_current = main_fine_current if main_fine < self.metadata.FineThreshold else main_coarse_current  # noqa

                # USB Coarse
                zero_offset = self.metadata.UsbCoarseZeroOffset
                cal_ref = self._usb_cal.ref_coarse
                zero_offset += self._usb_cal.zero_coarse
                try:
                    slope = self.metadata.UsbCoarseScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                usb_coarse_current = (usb_coarse - zero_offset) * slope
                # USB Fine
                zero_offset = self.metadata.UsbFineZeroOffset
                cal_ref = self._usb_cal.ref_fine
                zero_offset += self._usb_cal.zero_fine
                try:
                    slope = self.metadata.UsbFineScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                usb_fine_current = (usb_fine - zero_offset) * slope / 1000.
                usb_current = usb_fine_current if usb_fine < self.metadata.FineThreshold else usb_coarse_current  # noqa

                # AUX Coarse
                cal_ref = self._aux_cal.ref_coarse
                zero_offset = self._aux_cal.zero_coarse
                try:
                    slope = self.metadata.AuxCoarseScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                aux_coarse_current = (aux_coarse - zero_offset) * slope
                # AUX Fine
                cal_ref = self._aux_cal.ref_fine
                zero_offset = self._aux_cal.zero_fine
                try:
                    slope = self.metadata.AuxFineScale / (cal_ref - zero_offset)
                except ZeroDivisionError:
                    slope = 0.
                aux_fine_current = (aux_fine - zero_offset) * slope / 1000.
                aux_current = aux_fine_current if aux_fine < self.metadata.FineThreshold else aux_coarse_current  # noqa

                # Voltage
                main_voltage = main_voltage * self.metadata.ADCRatio * self.metadata.MainVoltageScale  # noqa
                usb_voltage = usb_voltage * self.metadata.ADCRatio * self.metadata.USBVoltageScale  # noqa

                return main_current, usb_current, aux_current, main_voltage, usb_voltage

        elif sampletype == SampleType.ZeroCal:
            self.zerocal_count += 1
            self._main_cal.add_zerocal_coarse(main_coarse)
            self._main_cal.add_zerocal_fine(main_fine)
            self._usb_cal.add_zerocal_coarse(usb_coarse)
            self._usb_cal.add_zerocal_fine(usb_fine)
            self._aux_cal.add_zerocal_coarse(aux_coarse)
            self._aux_cal.add_zerocal_fine(aux_fine)
            return None, None, None, None, None
        elif sampletype == SampleType.RefCal:
            self.refcal_count += 1
            self._main_cal.add_refcal_coarse(main_coarse)
            self._main_cal.add_refcal_fine(main_fine)
            self._usb_cal.add_refcal_coarse(usb_coarse)
            self._usb_cal.add_refcal_fine(usb_fine)
            self._aux_cal.add_refcal_coarse(aux_coarse)
            self._aux_cal.add_refcal_fine(aux_fine)
            return None, None, None, None, None
        elif sampletype == SampleType.Invalid:
            self.invalid_count += 1
            return None, None, None, None, None
        else:
            return None, None, None, None, None
        # some bogus type, default to all None
        return None, None, None, None, None


class StdoutHandler(MeasurementHandler):
    """Handler that emits sample data as tab seperated values to stdout."""

    def initialize(self, context):
        print("main_current", "usb_current", "aux_current", "main_voltage", "usb_voltage",
              sep="\t")

    def __call__(self, sample):
        (main_current, usb_current, aux_current,
         main_voltage, usb_voltage) = self._process_raw(sample)
        if main_current is not None:
            print(main_current, usb_current, aux_current, main_voltage, usb_voltage, sep="\t")


class FileHandler(MeasurementHandler):
    """Handler that emits sample data as binary packed double values.

    Structure is (main_current, usb_current, aux_current, main_voltage, usb_voltage),
    which is 5 items, or 40 bytes per sample.

    This can be read by numpy as:

        data = np.fromfile(file, dtype=np.double)
        data.shape = (-1, 5)
        data = data.transpose()

    This will give you columns containing the above values. That is, data[0] is
    main_current.
    """

    def initialize(self, context):
        super().initialize(context)
        fname = context.get("filename")
        self._packer = struct.Struct("=5d")
        if not fname:
            raise ValueError("No filename in context for Monsoon measurer.")
        self._output = open(fname, "wb")

    def __call__(self, sample):
        # values are (main_current, usb_current, aux_current, main_voltage, usb_voltage)
        values = self._process_raw(sample)
        if values[0] is not None:
            data = self._packer.pack(*values)
            self._output.write(data)

    def finalize(self, captured, dropped):
        super().finalize(captured, dropped)
        self._packer = None
        self._output.close()


class AverageHandler(MeasurementHandler):
    """Compute only average of all measurements.

    Emit a TSV format text of just the average of the run.
    """

    def initialize(self, context):
        self.main_current = self.usb_current = self.aux_current = self.main_voltage = self.usb_voltage = 0.  # noqa
        print("main_current", "usb_current", "aux_current", "main_voltage", "usb_voltage",
              sep="\t")

    def __call__(self, sample):
        main_current, usb_current, aux_current, main_voltage, usb_voltage = self._process_raw(sample)  # noqa
        if main_current is not None:
            self.main_current = (main_current + ((self.measure_count - 1) * self.main_current)) / self.measure_count
            self.main_voltage = (main_voltage + ((self.measure_count - 1) * self.main_voltage)) / self.measure_count
            self.usb_current = (usb_current + ((self.measure_count - 1) * self.usb_current)) / self.measure_count
            self.usb_voltage = (usb_voltage + ((self.measure_count - 1) * self.usb_voltage)) / self.measure_count
            self.aux_current = (aux_current + ((self.measure_count - 1) * self.aux_current)) / self.measure_count

    def finalize(self, counted, dropped):
        super().finalize(counted, dropped)
        print(self.main_current, self.usb_current, self.aux_current,
              self.main_voltage, self.usb_voltage, sep="\t")

    def __str__(self):
        s = [super().__str__()]
        s.append("Measured values:")
        s.append("  main_voltage: {:>11.4f} V".format(self.main_voltage))
        s.append("   usb_voltage: {:>11.4f} V".format(self.usb_voltage))
        s.append("  main_current: {:>11.4f} mA".format(self.main_current))
        s.append("   usb_current: {:>11.4f} mA".format(self.usb_current))
        s.append("   aux_current: {:>11.4f} ?".format(self.aux_current))
        return "\n".join(s)


class AveragePowerHandler(MeasurementHandler):
    """Handler for keeping a running average of measured values, and compute
    average power.

    After finalization, an instance of this object will have the following
    attributes.

    Attributes:
        main_current: float of average current on the main port, in mA.
        main_voltage: float of average voltage on the main port, in Volts.
        usb_current: float of average current on the USB port, in mA.
        usb_voltage: float of average voltage on the USB port, in Volts.
        main_power: float of average power during the measurement duration,
                    main port, in Watts.
        usb_power: float of average power during the measurement duration,
                   USB port, in Watts.
    """

    def initialize(self, context):
        self.main_current = self.usb_current = self.aux_current = self.main_voltage = self.usb_voltage = 0.  # noqa
        self.main_power = self.usb_power = 0.

    def __call__(self, sample):
        main_current, usb_current, aux_current, main_voltage, usb_voltage = self._process_raw(sample)  # noqa
        if main_current is not None:  # actual sample
            self.main_current = (main_current + ((self.measure_count - 1) * self.main_current)) / self.measure_count
            self.main_voltage = (main_voltage + ((self.measure_count - 1) * self.main_voltage)) / self.measure_count
            self.usb_current = (usb_current + ((self.measure_count - 1) * self.usb_current)) / self.measure_count
            self.usb_voltage = (usb_voltage + ((self.measure_count - 1) * self.usb_voltage)) / self.measure_count

    def finalize(self, counted, dropped):
        super().finalize(counted, dropped)
        self.main_power = self.main_voltage * (self.main_current / 1000.)  # W
        self.usb_power = self.usb_voltage * (self.usb_current / 1000.)  # W


class CountingHandler(MeasurementHandler):
    """Simply count the number of types of samples the Monsoon sends.

    Used for debugging and checking transfer performance.
    """

    def __call__(self, sample):
        SampleType = core.SampleType  # eliminate some dict lookups
        self.sample_count += 1
        (main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse, aux_fine,
         main_voltage, usb_voltage, main_coarse_gain, main_fine_gain, usb_gain,
         sampletype) = sample
        if sampletype == SampleType.Measurement:
            self.measure_count += 1
        elif sampletype == SampleType.ZeroCal:
            self.zerocal_count += 1
        elif sampletype == SampleType.RefCal:
            self.refcal_count += 1
        elif sampletype == SampleType.Invalid:
            self.invalid_count += 1


class Measurer:
    pass


class MonsoonCurrentMeasurer(Measurer):
    """Sets up a Monsoon for measuring from context dictionary.
    """

    def __init__(self, context):
        self.context = context
        self._dev = monsoon_simple.HVPM()

    def measure(self, handlerclass=None):
        """Perform a measurment run.

        Opens device, captures samples,and closes the device.

        Args:
            handlerclass: a subclass of MeasurementHandler that is callable. It
            will be instantiated here with the device metadata and context.

        Returns:
            A core.MeasurementResult instance.
        """
        ctx = self.context  # shorthand
        dev = self._dev
        dev.open(ctx["serialno"])
        channel = {
            "usb": core.VoltageChannel.MainAndUSB,
            "aux": core.VoltageChannel.MainAndAux,
        }.get(ctx.get("channel", "usb"))
        dev.voltage_channel = channel
        passthrough = {
            "on": core.USBPassthrough.On,
            "off": core.USBPassthrough.Off,
            "auto": core.USBPassthrough.Auto,
        }.get(ctx.get("passthrough", "auto"))
        dev.usb_passthrough = passthrough
        dev.voltage = ctx["voltage"]
        if handlerclass is None:
            handlerclass = {
                "stdout": StdoutHandler,
                "count": CountingHandler,
                "average": AverageHandler,
                "power": AveragePowerHandler,
                "file": FileHandler,
            }.get(ctx.get("output"))
        if handlerclass is None or not issubclass(handlerclass, MeasurementHandler):
            raise ValueError("Measure handler class must be standard name or "
                             "subclass of MeasurementHandler.")
        handler = handlerclass(ctx, dev.info)
        # Perform the capture run.
        ctx["start_time"] = time.time()
        try:
            captured, dropped = dev.capture(samples=ctx["numsamples"],
                                            duration=ctx["duration"],
                                            handler=handler,
                                            calsamples=ctx.get("calsamples", 1250),
                                            startdelay=ctx.get("delay", 0))
        finally:
            dev.close()
        handler.finalize(captured, dropped)
        return core.MeasurementResult.from_context_and_handler(ctx, handler)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
