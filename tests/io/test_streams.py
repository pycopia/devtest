#!/usr/bin/env python3.7

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test io.streams module.
"""

import os
import signal

import pytest

from devtest.timers import FDTimer
from devtest.signals import FDSignals
from devtest.io import reactor

from devtest.io import streams


async def _timer_test(timer):
    timer.settime(1, 1)
    timer = streams.ReadableStream(timer)
    count = 0
    while count < 5:
        count += await timer.read()
        print("ticked")


async def _timer_test_main():
    timer = FDTimer(nonblocking=1)
    tt = await reactor.spawn(_timer_test, timer)
    await tt.join()
    timer.stop()


async def _signal_test(sigs, mypid):
    sigstream = streams.ReadableStream(sigs)
    count = 0
    while count < 5:
        signal.raise_signal(signal.SIGUSR1)
        siginfo = await sigstream.read()
        assert siginfo.signo == signal.SIGUSR1
        count += 1


async def _signals_test_main():
    sigs = FDSignals({signal.SIGUSR1}, nonblocking=True)
    task = await reactor.spawn(_signal_test, sigs, os.getpid())
    await task.join()
    sigs.close()



class TestReadableStreams:

    def test_fdtimer(self):
        kern = reactor.get_kernel()
        kern.run(_timer_test_main)

    def test_fdsignals(self):
        kern = reactor.get_kernel()
        kern.run(_signals_test_main)
