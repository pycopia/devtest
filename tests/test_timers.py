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

"""Test timers module.
"""


import time
import signal

import pytest

from devtest import timers

_signaled = None


def _sighandler(s, f):
    global _signaled
    _signaled = True


def _sighandler_exception(s, f):
    global _signaled
    _signaled = True
    raise IOError("fake IO error")


def test_nanosleep():
    start = time.time()
    timers.nanosleep(5)
    stop = time.time()
    print(stop - start)
    assert (stop - start) < 5.01 and (stop-start) > 4.999


def test_nanosleep_with_alarm():
    old = signal.signal(signal.SIGALRM, _sighandler)
    signal.alarm(2)
    start = time.time()
    timers.nanosleep(5)
    stop = time.time()
    print(stop - start)
    signal.signal(signal.SIGALRM, old)
    assert (stop - start) < 5.01 and (stop-start) > 4.999
    assert _signaled is True


def test_nanosleep_with_alarm():
    old = signal.signal(signal.SIGALRM, _sighandler_exception)
    signal.alarm(2)
    start = time.time()
    with pytest.raises(IOError):
        timers.nanosleep(5)
    stop = time.time()
    print(stop - start)
    signal.signal(signal.SIGALRM, old)
    assert (stop - start) < 2.01 and (stop-start) > 1.999
    assert _signaled is True



# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
