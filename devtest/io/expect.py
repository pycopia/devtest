# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provide Expect-like functionality over a file-like object.
"""

import re
import os
import fnmatch
from functools import lru_cache, partial

from devtest import ringbuffer
from devtest.os import time
from devtest.textutils.stringmatch import compile_exact


# matching types
EXACT = 1  # string match (fastest)
GLOB = 2   # POSIX shell style match
REGEX = 3  # Slower but featureful RE match


class ExpectError(Exception):
    """Raised when the unexpected happens."""
    pass


class Expect:
    """A wrapper for a file-like object that provides Expect functionality on
    top of it.

    The send and expect methods work with text (latin1 encoded). The read/write
    methods work with bytes. The underlaying file-like object should have a
    bytes interface.

    The timeout option is a hard timeout for most IO operations.
    """

    EXACT = EXACT
    GLOB = GLOB
    REGEX = REGEX

    def __init__(self, fo, prompt="$ ", timeout=90.0):
        if hasattr(fo, "fileno"):
            self._fo = fo
        else:
            raise ValueError("Expect: first parameter should be a file-like object.")
        self.default_timeout = timeout
        self._prompt = prompt.encode("ascii")
        self._inbuf = ringbuffer.RingBuffer(4096)

    def fileno(self):
        return self._fo.fileno()

    def close(self):
        if self._fo is not None:
            self._fo.close()
            self._fo = None

    @property
    def closed(self):
        return not bool(self._fo)

    @property
    def prompt(self):
        return self._prompt.decode("ascii")

    @prompt.setter
    def prompt(self, prompt):
        self._prompt = prompt.encode("ascii")

    @lru_cache()
    def _get_re(self, patt, mtype=EXACT, callback=None):
        if callback is not None:
            if not callable(callback):
                raise ValueError("Callback must be a callable.")
        if mtype == EXACT:
            return (compile_exact(patt), callback)
        elif mtype == GLOB:
            return (re.compile(fnmatch.translate(patt)), callback)
        elif mtype == REGEX:
            return (re.compile(patt), callback)

    def _get_search_list(self, patt, mtype, callback, searchlist=None):
        if searchlist is None:
            searchlist = []
        ptype = type(patt)
        if ptype is str:
            searchlist.append(self._get_re(patt.encode("latin1"), mtype, callback))
        elif ptype is bytes:
            searchlist.append(self._get_re(patt, mtype, callback))
        elif ptype is tuple:
            searchlist.append(self._get_re(*patt))
        elif ptype is TimeoutMatch:
            searchlist.append((patt, callback))
        elif ptype is list:
            for p in patt:
                self._get_search_list(p, mtype, callback, searchlist)
        return searchlist

    def send(self, text, timeout=None):
        timeout = timeout or self.default_timeout
        return time.iotimeout(partial(self._fo.write, text.encode("latin1")),
                              timeout)

    def send_slow(self, data):
        if isinstance(data, str):
            data = data.encode("latin1")
        for c in data:
            self._fo.write(bytes([c]))
            time.delay(0.1)
        return len(data)

    def flush(self):
        try:
            self._fo.flush()
        except AttributeError:
            pass

    def expect(self, patt, mtype=EXACT, callback=None, timeout=None):
        timeout = timeout or self.default_timeout
        searchlist = self._get_search_list(patt, mtype, callback)
        if not searchlist:
            raise ExpectError("Empty expect search.")
        time.iotimeout(self._fill_buf, timeout)
        matchbuf = bytes()
        while 1:
            c = self._inbuf.read(1)
            if not c:
                time.iotimeout(self._fill_buf, timeout)
                continue
            matchbuf += c
            for index, (so, cb) in enumerate(searchlist):
                mo = so.search(matchbuf)
                if mo:
                    mo.string = mo.string.decode("latin1")
                    if cb is not None:
                        cb(mo)
                    return mo, index

    @staticmethod
    def timeoutmatch(value):
        return TimeoutMatch(value)

    def _fill_buf(self):
        inbuf = self._inbuf
        inbuf.write(self._fo.read(inbuf.freespace))

    def read_until_prompt(self, timeout=None):
        mo, i = self.expect(self._prompt, timeout=timeout)
        if mo:
            return mo.string[:-len(self._prompt)]

    def read_until(self, text, timeout=None):
        mo, _ = self.expect(text, timeout=timeout)
        if mo:
            return mo.string[:-len(text)]

    def read(self, amt=-1, timeout=None):
        timeout = timeout or self.default_timeout
        if len(self._inbuf) > 0:
            return self._inbuf.read(amt)
        return time.iotimeout(partial(self._fo.read, amt), timeout)

    def write(self, data):
        return self._fo.write(data)

    def readline(self, timeout=None):
        timeout = timeout or self.default_timeout
        if self._inbuf:
            bd = self._inbuf.read()
            i = bd.find(b'\n')
            if i >= 0:
                line = bd[:i + 1]
                self._inbuf.write(bd[i + 1:])
                return line
            else:
                return bd + self._fo.readline()
        else:
            return time.iotimeout(self._fo.readline, timeout)

    def readlines(self):
        for line in self._fo.readlines():
            yield line

    def delay(self, time):
        time.delay(time)

    def isatty(self):
        return os.isatty(self._fo.fileno())


# Basically polymorphic to RE search objects.
class TimeoutMatch:
    """A weak timeout.

    Works when data is available but nothing matches for some time.
    Add this to an expect expression to match on a timeout value.

    Returns a TimeoutMatchObject when a call to the search method happens
    `timeout` seconds after the first time it was called.
    """
    def __init__(self, timeout: float):
        self._timeout = timeout
        self._starttime = None

    @property
    def timeout(self):
        return self._timeout

    def search(self, text, pos=0, endpos=2147483647):
        if self._starttime is None:
            self._starttime = time.now()
            return None
        if (time.now() - self._starttime) >= self._timeout:
            return TimeoutMatchObject(text)
        else:
            return None

    match = search


class TimeoutMatchObject:
    def __init__(self, string):
        self.string = string

    def __bool__(self):
        return True


def _test(argv):
    from devtest.os import process
    from devtest.textutils.stringmatch import StringMatchObject
    # With process
    proc = process.start_process(["/bin/cat", "-u", "-"])
    exp = Expect(proc)
    exp.send("echo me\n")
    mo, index = exp.expect("echo")
    if mo:
        print(mo)
        assert type(mo) is StringMatchObject
        print(mo.string)
        assert mo.string == "echo"
    else:
        raise AssertionError("Did not see expected response.")

    exp.send("one\ntwo\nthree\n")
    mo, index = exp.expect(["alpha", "beta", "three"])
    if mo:
        assert index == 2
        assert mo.string.endswith("three")
    else:
        raise AssertionError("Did not see expected response.")

    exp.close()

    proc = process.start_process(["/bin/sleep", "30"])
    exp = Expect(proc)
    try:
        exp.expect(["zzz", TimeoutMatch(3.0)], timeout=5.0)
    except TimeoutError:
        pass
    else:
        exp.close()
        raise AssertionError("Did not see expected TimeoutError.")
    exp.close()


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
