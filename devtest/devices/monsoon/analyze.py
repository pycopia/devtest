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

"""Methods and objects to analyze captured samples.
"""

import numpy as np
from matplotlib.backends import backend_agg
from matplotlib import figure
from matplotlib import collections as mpl_collections

from devtest.qa import signals

from .core import MeasurementResult


class SampleData:
    """Monsoon sample data plus metadata.

    Attributes:
        samples: ndarray of all samples (from samplefile).
        columns: List of columns labels, in order of columns in samples.
        units: List of unit labels, in order of columns in samples.
        start_time: float of time measurement run started, unix time.
        sample_rate: int number of samples per second in samples array.
        voltage: The voltage set during measurement.
        dropped: Number of samples dropped by device.
        sample_count: number of raw data samples (includes ref and cal samples).
        measure_count: number of actual, measurement data samples.
        samplefile: name of the file where raw samples are stored.
        heading: str of column names and units suitable for printing a table.
        main_current: vector of main current samples only, and unit string.
        main_voltage: vector of main voltage readings only, and unit string.
    """

    def __init__(self, samples=None, result=None):
        """Initialize this SampleData from samples array and MeasurementResult.
        """
        self._samples = samples
        if result is not None:
            self.columns = result.columns
            self.units = result.units
            self.start_time = result.start_time
            self.sample_rate = result.sample_rate
            self.voltage = result.voltage
            self.dropped = result.dropped
            self.sample_count = result.sample_count  # total samples
            self.measure_count = result.measure_count  # samples counting for measurement
            self.samplefile = result.samplefile
        else:
            self.columns = None
            self.units = None
            self.start_time = None
            self.sample_rate = None
            self.voltage = None
            self.dropped = None
            self.sample_count = None
            self.samplefile = None

    def __str__(self):
        s = [self.heading]
        s.append(repr(self.samples))
        return "\n".join(s)

    def get_column(self, name):
        """Return column data and unit of column."""
        index = self.columns.index(name)
        return self.samples[index], self.units[index]

    def get_time_axis(self, absolute=False):
        """Create a time datapoint axis from the measure data.

        Use the measure count and sample rate from the result.
        """
        offset = self.start_time if absolute else 0.0
        times = np.arange(offset,
                          offset + (self.measure_count / self.sample_rate),
                          1.0 / self.sample_rate,
                          np.float64)
        assert len(times) == self.measure_count
        return times

    def get_xy(self, name, absolute=False):
        """Return tuple of time and column value arrays, x unit, y unit.
        """
        col, unit = self.get_column(name)
        times = self.get_time_axis(absolute=absolute)
        return times, col, "s", unit

    @property
    def samples(self):
        """All samples from sample file, if available.

        Returns:
            ndarray of all sample columns.
        """
        if self._samples is None:
            if self.samplefile:
                self._samples = SampleData.read_file(self.samplefile)
        return self._samples

    @property
    def heading(self):
        """String suitable for printing a header line."""
        heads = ["{} ({})".format(n, u) for n, u in zip(self.columns, self.units)]
        return " | ".join(heads)

    @property
    def main_current(self):
        """The main_current column, as ndarray vector."""
        return self.get_column("main_current")

    @property
    def main_voltage(self):
        """The main_voltage column, as ndarray vector."""
        return self.get_column("main_voltage")

    @classmethod
    def from_result(cls, result):
        """Read result object and load samples from samplefile, and metadata.
        """
        return cls(None, result)

    @classmethod
    def from_file(cls, filename):
        """Read raw samples from a file without metadata.
        """
        data = SampleData.read_file(filename)
        return cls(data, None)

    @staticmethod
    def read_file(filename):
        """Read a binary file as written by the FileHandler and convert it to
        columns.

        Return:
            ndarray
        """
        data = np.fromfile(filename, dtype=np.double)
        data.shape = (-1, 5)
        return data.transpose()


def plot_samples(samples, events=None, column="main_current", width=8):
    """Build a Figure with samples plotted.

    Uses matplotlib and the Agg backend.

    Arguments:
        samples: A SampleData object.
        events: optional list of times (floats) within sample range to put markers.
        column: The name (str) of the sample column to plot.
        width: The width, in inches, of the Figure.

    Returns:
        A Figure instance ready to be modified, displayed, or saved.
    """
    # Get the X and X data and units.
    time, colvector, xunit, yunit = samples.get_xy(column)
    # Make the figure and axes using low-level class API to avoid using local
    # configuration.
    fig = figure.Figure(figsize=(width, width * 0.75), dpi=95,
                        facecolor="white", edgecolor="white",
                        frameon=True)
    backend_agg.FigureCanvasAgg(fig)  # The figure keeps a reference to backend.
    axs = fig.subplots(nrows=1, ncols=1,
                       sharex=False, sharey=False,
                       squeeze=True, subplot_kw=None,
                       gridspec_kw=None)
    # Plotting at max resolution just makes the plot look solid.
    # Downsample to pixel resolution.
    downsample_to = int(fig.get_size_inches()[0] * fig.dpi)
    Nx = colvector.shape[0]
    stride = Nx // downsample_to
    downsampled = np.fromiter((np.mean(a) for a in colvector[::stride]),
                              colvector.dtype, count=downsample_to)
    newtimes = np.arange(0, downsample_to) * (time[1] - time[0]) * Nx / float(downsample_to) + time[0]  # noqa

    axs.plot(newtimes, downsampled)
    axs.set_title("{} over time{}.".format(column,
                                           " with events" if events else ""))
    if events is not None:
        events.sort()
        offset = downsampled.min()
        length = offset * 2
        evl = mpl_collections.EventCollection(events,
                                              color=[(1, 0, 0), (0, 1, 0)],
                                              linelength=length,
                                              lineoffset=offset,
                                              zorder=1)
        axs.add_collection(evl)

    axs.set_xlabel('time ({})'. format(xunit))
    axs.set_ylabel("{} ({})".format(column, yunit))
    axs.grid(True)
    return fig


def to_monsoon_sampledata(analyzer, data=None, config=None):
    """Signal handler for analysis system."""
    if isinstance(data, MeasurementResult):
        data.samplefile = analyzer.fix_path(data.samplefile)
        return SampleData.from_result(data)


signals.data_convert.connect(to_monsoon_sampledata)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
