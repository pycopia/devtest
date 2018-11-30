#!/usr/bin/env python3.6


"""Capture Monsoon data to file.
"""

import h5py

from devtest.devices.monsoon import simple as monsoon_simple
from devtest.devices.monsoon import core


class MeasurementHandler:
    def __init__(self, context, metadata):
        self.metadata = metadata
        self.sample_count = 0
        self.cal_count = 0
        self.captured = 0
        self.dropped = 0
        self.measure_count = 0
        self.zerocal_count = 0
        self.refcal_count = 0
        self.invalid_count = 0

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
        # 8 AuxCoarse 2 SInt16 Calibration or measurement value.
        # 10 AuxFine 2 SInt16 Calibration or measurement value.
        # 12 Main Voltage 2 UInt16 Main Voltage measurement, or Aux voltage measurement if setVoltageChannel = 1
        # 14 USB Voltage 2 UInt16 USB Voltage
        # 16 Main Gain 1 Measurement gain control.
        # 17 USB Gain 1 Measurement gain control.
        (main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse, aux_fine,
         main_voltage, usb_voltage, main_gain, usb_gain) = sample
        # TODO



class HDF5Handler(MeasurementHandler):

    def __call__(self, sample):
        self.sample_count += 1


class CountingHandler(MeasurementHandler):

    def __call__(self, sample):
        SampleType = core.SampleType  # eliminate some dict lookups
        self.sample_count += 1
        (main_coarse, main_fine, usb_coarse, usb_fine, aux_coarse, aux_fine,
         main_voltage, usb_voltage, main_gain, usb_gain) = sample
        sampletype = main_gain & 0x30
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
