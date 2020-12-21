#!/usr/bin/env python3.9

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for devtest.signals module.
"""

import os
import sys
import time
import signal
import selectors
import threading

import pytest

from devtest import signals


def _signal_later(delay, sig):
    def _sigusr(pid):
        time.sleep(delay)
        os.kill(pid, sig)
    t = threading.Thread(target=_sigusr, args=(os.getpid(),))
    t.start()
    return t


@pytest.mark.skipif(sys.platform != "linux", reason="Only available on Linux")
class TestFDSignals:

    def test_create(self):
        sigs = signals.FDSignals({signal.SIGUSR1})
        assert type(sigs) is signals.FDSignals
        sigs.close()

    def test_create_nonblocking(self):
        sigs = signals.FDSignals({signal.SIGUSR1}, nonblocking=True)
        assert type(sigs) is signals.FDSignals
        sigs.close()

    def test_select(self):
        sigs = signals.FDSignals({signal.SIGUSR1}, nonblocking=True)
        siginfo = None
        t = _signal_later(1, signal.SIGUSR1)
        with selectors.DefaultSelector() as sel:
            rkey = sel.register(sigs, selectors.EVENT_READ)
            resp = sel.select()
        for key, event in resp:
            if event == selectors.EVENT_READ:
                siginfo = key.fileobj.read()
        assert isinstance(siginfo, signals.SignalInfo)
        print(siginfo)
        sigs.close()
        t.join()
        assert siginfo.signo == signal.SIGUSR1

    def test_multi_select(self):
        sigs = signals.FDSignals({signal.SIGUSR1, signal.SIGUSR2}, nonblocking=True)
        siginfo = None
        t1 = _signal_later(1, signal.SIGUSR1)
        t2 = _signal_later(1, signal.SIGUSR2)
        t3 = _signal_later(2, signal.SIGUSR1)
        try:
            with selectors.DefaultSelector() as sel:
                rkey = sel.register(sigs, selectors.EVENT_READ)
                state = 1
                while True:
                    resp = sel.select()
                    if state >= 3:
                        break
                    for key, event in resp:
                        if event == selectors.EVENT_READ:
                            siginfo = key.fileobj.read()
                            if state == 1:
                                assert siginfo.signo == signal.SIGUSR1
                                state += 1
                            elif state == 2:
                                assert siginfo.signo == signal.SIGUSR2
                                state += 1
        finally:
            sigs.close()
            t1.join()
            t2.join()
            t3.join()
