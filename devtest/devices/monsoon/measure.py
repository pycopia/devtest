#!/usr/bin/env python3.6


"""Capture Monsoon data to file.
"""

import h5py

from devtest.devices.monsoon import simple as monsoon_simple
from devtest.devices.monsoon import core


class MeasurementHandler:
    def __init__(self, context, metadata):
        self.metadata = metadata
        self.captured = 0
        self.dropped = 0

    def finalize(self, captured, dropped):
        self.captured = captured
        self.dropped = dropped

    def __call__(self, sample):
        pass

    def __str__(self):
        return "captured: {}, dropped: {}".format(self.captured, self.dropped)


class RawHandler(MeasurementHandler):
    pass


class HDF5Handler(MeasurementHandler):
    pass


class CountingHandler(MeasurementHandler):

    def __init__(self, context, metadata):
        super().__init__(context, metadata)
        self.sample_count = 0
        self.cal_count = 0

    def __call__(self, sample):
        self.sample_count += 1

    def __str__(self):
        s = [super().__str__()]
        s.append("Counted {} samples.".format(self.sample_count))
        return "\n".join(s)


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
                                        handler=handler)
        dev.close()
        handler.finalize(captured, dropped)
        return handler



if __name__ == "__main__":
    pass

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
