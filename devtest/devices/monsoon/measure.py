#!/usr/bin/env python3.6


"""Capture Monsoon data to file.
"""

import collections
import math

import h5py

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
    def __init__(self, context, metadata, calsize=5):
        self.metadata = metadata
        self.sample_count = 0
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

    @property
    def is_calibrated(self):
        return (self._main_cal.is_calibrated and self._usb_cal.is_calibrated and
                self._aux_cal.is_calibrated)

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


class RawHandler(MeasurementHandler):

    def __call__(self, sample):
        SampleType = core.SampleType
        self.sample_count += 1
        # 0 MainCoarse 2 UInt16 Calibration or measurement value.
        # 2 MainFine 2 UInt16 Calibration or measurement value.
        # 4 USBCoarse 2 UInt16 Calibration or measurement value.
        # 6 USBFine 2 UInt16 Calibration or measurement value.
        # 8 AuxCoarse 2 UInt16 Calibration or measurement value.
        # 10 AuxFine 2 UInt16 Calibration or measurement value.
        # 12 Main Voltage 2 UInt16 Main Voltage measurement, or Aux voltage measurement if setVoltageChannel = 1
        # 14 USB Voltage 2 UInt16 USB Voltage
        (main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse, aux_fine,
         main_voltage, usb_voltage, main_coarse_gain, main_fine_gain, usb_gain,
         sampletype) = sample
        if sampletype == SampleType.Measurement:
            self.measure_count += 1
            if self.is_calibrated:
                # Main Coarse
                scale = self.metadata.MainCoarseScale
                zero_offset = self.metadata.MainCoarseZeroOffset
                cal_ref = self._main_cal.ref_coarse
                cal_zero = self._main_cal.zero_coarse
                zero_offset += cal_zero
                if not math.isclose(cal_ref, zero_offset):
                    slope = scale / (cal_ref - zero_offset)
                else:
                    slope = 0.
                main_coarse_current = (main_coarse - zero_offset) * slope
#                #Main Fine
                scale = self.metadata.MainFineScale
                zero_offset = self.metadata.MainFineZeroOffset
                cal_ref = self._main_cal.ref_fine
                cal_zero = self._main_cal.zero_fine
                zero_offset += cal_zero
                if not math.isclose(cal_ref, zero_offset):
                    slope = scale / (cal_ref - zero_offset)
                else:
                    slope = 0.
                main_fine_current = (main_fine - zero_offset) * slope / 1000.
                main_current = main_fine_current if main_fine < self.metadata.FineThreshold else main_coarse_current
                print("XXX main current:", main_current)

#                #USB Coarse
                scale = self.metadata.UsbCoarseScale
                zero_offset = self.metadata.UsbCoarseZeroOffset
                cal_ref = self._usb_cal.ref_coarse
                cal_zero = self._usb_cal.zero_coarse
                zero_offset += cal_zero
                if not math.isclose(cal_ref, zero_offset):
                    slope = scale / (cal_ref - zero_offset)
                else:
                    slope = 0.
                usb_coarse_current = (usb_coarse - zero_offset) * slope
#                #USB Fine
                scale = self.metadata.UsbFineScale
                zero_offset = self.metadata.UsbFineZeroOffset
                cal_ref = self._usb_cal.ref_fine
                cal_zero = self._usb_cal.zero_fine
                zero_offset += cal_zero
                if not math.isclose(cal_ref, zero_offset):
                    slope = scale / (cal_ref - zero_offset)
                else:
                    slope = 0.
                usb_fine_current = (usb_fine - zero_offset) * slope / 1000.
                usb_current = usb_fine_current if usb_fine < self.metadata.FineThreshold else usb_coarse_current
                print("XXX USB", usb_current)

        elif sampletype == SampleType.ZeroCal:
            self.zerocal_count += 1
            self._main_cal.add_zerocal_coarse(main_coarse)
            self._main_cal.add_zerocal_fine(main_fine)
            self._usb_cal.add_zerocal_coarse(usb_coarse)
            self._usb_cal.add_zerocal_fine(usb_fine)
            self._aux_cal.add_zerocal_coarse(aux_coarse)
            self._aux_cal.add_zerocal_fine(aux_fine)
        elif sampletype == SampleType.RefCal:
            self.refcal_count += 1
            self._main_cal.add_refcal_coarse(main_coarse)
            self._main_cal.add_refcal_fine(main_fine)
            self._usb_cal.add_refcal_coarse(usb_coarse)
            self._usb_cal.add_refcal_fine(usb_fine)
            self._aux_cal.add_refcal_coarse(aux_coarse)
            self._aux_cal.add_refcal_fine(aux_fine)
        elif sampletype == SampleType.Invalid:
            self.invalid_count += 1


class HDF5Handler(MeasurementHandler):

    def __call__(self, sample):
        self.sample_count += 1


class CountingHandler(MeasurementHandler):

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

    def __init__(self, context):
        self.context = context
        self._dev = monsoon_simple.HVPM()

    def measure(self):
        ctx = self.context  # shorthand
        dev = self._dev
        dev.open(ctx["serialno"])
        dev.voltage_channel = core.VoltageChannel.MainAndUSB
        passthrough = {
                "on": core.USBPassthrough.On,
                "off": core.USBPassthrough.Off,
                "auto": core.USBPassthrough.Auto,
        }.get(ctx["passthrough"], core.USBPassthrough.Auto)
        dev.usb_passthrough = passthrough
        dev.voltage = ctx["voltage"]
        handlerclass = {
                "raw": RawHandler,
                "count": CountingHandler,
                "hdf5": HDF5Handler,
        }.get(ctx["output"], HDF5Handler)
        handler = handlerclass(ctx, dev.info)
        # Perform the capture run.
        captured, dropped = dev.capture(samples=ctx["numsamples"],
                                        duration=ctx["duration"],
                                        handler=handler,
                                        calsamples=ctx.get("calsamples", 1250))
        dev.close()
        handler.finalize(captured, dropped)
        return handler



if __name__ == "__main__":
    pass

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
