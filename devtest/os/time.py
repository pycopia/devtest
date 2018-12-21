# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Timing related functions that also work with the asynchronous core framework.
"""

from __future__ import generator_stop

import time
import signal
from functools import wraps

from devtest.io.reactor import get_kernel, sleep


__all__ = ['delay', 'delay_before', 'delay_after']

now = time.time


def delay(secs):
    return get_kernel().run(sleep(secs))


def delay_before(seconds):
    """Decorator that delays <value> seconds before code in method actually runs.
    """
    def _wrapper(f):
        @wraps(f)
        def _lambda(*iargs, **ikwargs):
            delay(seconds)
            return f(*iargs, **ikwargs)
        return _lambda
    return _wrapper


def delay_after(seconds):
    """Decorator that delays <value> seconds after code in method actually runs before returning.
    """
    def _wrapper(f):
        @wraps(f)
        def _lambda(*iargs, **ikwargs):
            rv = f(*iargs, **ikwargs)
            delay(seconds)
            return rv
        return _lambda
    return _wrapper


def iotimeout(function, *args, timeout=5.0):
    def _timeout(sig, st):
        raise TimeoutError("IO operation timed out for {!r}.".format(function.__name__))

    signal.siginterrupt(signal.SIGALRM, True)
    oldhandler = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout, 0)
    try:
        return function(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        signal.signal(signal.SIGALRM, oldhandler)
        signal.siginterrupt(signal.SIGALRM, False)


# Unit tests
if __name__ == "__main__":
    import math

    delay_start = now()
    delay(2)
    delay_end = now()
    dt = delay_end - delay_start
    print(dt)
    assert math.isclose(dt, 2.0, rel_tol=0.01)

    @delay_before(2)
    def need_delayed_start():
        print("Time is now:", now())

    st = now()
    need_delayed_start()
    se = now()
    assert math.isclose(se - st, 2.0, rel_tol=0.01)

    @delay_after(2)
    def need_delayed_end():
        print("Time is now:", now())

    st = now()
    need_delayed_end()
    se = now()
    assert math.isclose(se - st, 2.0, rel_tol=0.01)

    @delay_before(2)
    @delay_after(2)
    def need_delayed_bracketed():
        print("Time is now:", now())

    st = now()
    need_delayed_bracketed()
    se = now()
    assert math.isclose(se - st, 4.0, rel_tol=0.01)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
