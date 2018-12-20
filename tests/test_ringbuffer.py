#!/usr/bin/env python3

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
RingBuffer unit tests.
"""

import pytest

from devtest import ringbuffer


@pytest.fixture
def rb():
    return ringbuffer.RingBuffer(4096)


class TestRingBuffer:

    def test_create(self):
        rb = ringbuffer.RingBuffer()
        assert rb is not None

    def test_bad_create(self):
        with pytest.raises(ValueError):
            ringbuffer.RingBuffer(1000)

    def test_size(self, rb):
        assert rb.size == 4096

    def test_write(self, rb):
        DATA = b"This is data\n"
        writ = rb.write(DATA)
        assert writ == len(DATA)
        assert rb[1] == ord(b"h")

    def test_basic_write_read(self, rb):
        DATA = b"This is data\n"
        rb.write(DATA)
        r = rb.read()
        assert r == DATA

    def test_clear(self, rb):
        DATA = b"This is data\n"
        rb.write(DATA)
        assert len(rb) == len(DATA)
        rb.clear()
        assert len(rb) == 0

    def test_write_read(self, rb):
        DATA = b"This is data\n"
        rb.write(DATA)
        rb.write(DATA)
        assert len(rb) == len(DATA) * 2
        r = rb.read(1000)
        assert r == DATA + DATA
        assert len(rb) == 0

    def test_read_empty(self, rb):
        assert rb.read() == b""

    def test_write_large(self, rb):
        rb.write(b"0123456789ABCDEF" * 256)
        assert len(rb) == 4095

    def test_read_small(self, rb):
        DATA = b"0123456789ABCDEF"
        rb.write(DATA * 256)
        r = rb.read(16)
        assert len(r) == 16
        assert len(rb) == 4095 - 16

    def test_read_multi(self, rb):
        DATA = b"0123456789ABCDEF"
        rb.write(DATA * 256)
        r = rb.read(16)
        assert r == DATA
        r = rb.read(17)
        assert r == DATA + b"0"

    def test_read_over(self, rb):
        DATA = b"0123456789ABCDEF"
        rb.write(DATA * 256)
        rb.read(len(DATA) * 255)
        r = rb.read(32)
        assert r == b"0123456789ABCDE"
        r = rb.read(32)
        assert r == b""
        rb.write(DATA)
        r = rb.read(32)
        assert r == DATA

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
