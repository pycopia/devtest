"""
Minimal terminal responder implemented as a filter.
"""

from __future__ import generator_stop

import sys
import struct
from functools import partial

from devtest import ringbuffer
from devtest.textutils import fsm
from devtest.os import time

ANY = fsm.ANY

# FSM states for Terminal
DEFAULT = 0
ESC = 1
CSI = 2
CSIDIGIT1 = 3
SEMICOLON = 4
ENDLINE = 5
INPROMPT = 1000

# Support for filtering out KDP muxed data.
SKDP_START_CHAR = b'\xFA'
SKDP_END_CHAR = b'\xFB'
SKDP_ESC_CHAR = b'\xFE'

DS_WAITSTART = 10
DS_READING = 11
DS_ESCAPED = 12


byte = struct.Struct("B").pack


class Terminal:
    """IO shim that filters terminal escape codes, such as color codes. Also
    responds to inquiries.

    Reads and writes bytes only.
    """

    def __init__(self, fileobj, prompt="# ", timeout=60.0):
        assert hasattr(fileobj, "write")
        self._fo = fileobj
        self._prompt = prompt.encode("ascii")
        self._timeout = float(timeout)
        self._atprompt = False
        self._atendline = False
        self.initialize()
        self.reset()

    def __repr__(self):
        return "{}({!r}, prompt={!r}, timeout={!r})".format(self.__class__.__name__,
                self._fo, self.prompt, self._timeout)

    def fileno(self):
        return self._fo.fileno()

    def close(self):
        if self._fo is not None:
            self._fo.close()
            self._fo = None

    def initialize(self):
        self._fsm = f = fsm.FiniteStateMachine(DEFAULT)
        # normal text
        f.add_default_transition(self._putin, DEFAULT)
        f.add_transition(ord('\x1b'), DEFAULT, None, ESC)
        f.add_transition(ANY, DEFAULT, self._putin, DEFAULT)
        f.add_transition(ord('\x1b'), ESC, None, ESC)
        f.add_transition(ord('['), ESC, None, CSI)
        f.add_transition(ord('c'), CSI, self._identify, DEFAULT)
        f.add_transition_list(b'0123456789', CSI, self._csidigitstart, CSIDIGIT1)
        f.add_transition(ANY, CSI, None, DEFAULT)
        f.add_transition_list(b'0123456789', CSIDIGIT1, self._csidigit, CSIDIGIT1)
        f.add_transition(ord(';'), CSIDIGIT1, self._csidigitdone, SEMICOLON)
        f.add_transition_list(b'0123456789', SEMICOLON, self._csidigitstart, CSIDIGIT1)
        f.add_transition(ord('n'), CSIDIGIT1, self._report, DEFAULT)
        f.add_transition(ord('m'), CSIDIGIT1, self._sda, DEFAULT)
        # consumes any other CSI
        f.add_transition(ANY, CSIDIGIT1, self._csireset, DEFAULT)
        # deal with KDP escaping
        f.add_transition(ord(SKDP_ESC_CHAR), DEFAULT, None, DS_ESCAPED)
        f.add_transition(ANY, DS_ESCAPED, self._esc_kdp, DEFAULT)
        # consume KDP protocol
        f.add_transition(ord(SKDP_START_CHAR), DEFAULT, None, DS_READING)
        f.add_transition(ord(SKDP_START_CHAR), DS_READING, None, DS_READING)
        f.add_transition(ord(SKDP_ESC_CHAR), DS_READING, None, DS_READING)
        f.add_transition(ord(SKDP_END_CHAR), DS_READING, None, DEFAULT)
        f.add_transition(ANY, DS_READING, None, DS_READING)

    def reset(self):
        self._inbuf = bytearray()

    @property
    def prompt(self):
        return self._prompt.decode("ascii")

    @prompt.setter
    def prompt(self, prompt):
        self._prompt = prompt.encode("ascii")

    def write(self, data):
        return self._fo.write(data)

    def write_slow(self, data):
        for c in data:
            self._fo.write(byte(c))
            time.delay(0.1)
        return len(data)

    def flush(self):
        self._fo.flush()

    def read(self, amt):
        buf = self._inbuf
        self._read()
        if len(buf) <= amt:
            data = bytes(buf)
            buf.clear()
        else:
            data = bytes(buf[:amt])
            del buf[:amt]
        return data

    def readline(self):
        buf = self._inbuf
        self._read()
        while True:
            nl_index = buf.find(b'\n')
            if nl_index >= 0:
                resp = bytes(buf[:nl_index + 1])
                del buf[:nl_index + 1]
                return resp
            self._read()

    def _read(self):
        inp = time.iotimeout(partial(self._fo.read, 4096), self._timeout)
        self._fsm.process_string(inp)

    def read_until(self, substr):
        buf = self._inbuf
        self._read()
        while True:
            index = buf.find(substr)
            if index >= 0:
                resp = bytes(buf[:index])
                del buf[:index + len(substr)]
                return resp
            self._read()

    def read_until_prompt(self):
        return self.read_until(self._prompt)

    # code handlers
    def _putin(self, c, fsm):
        self._inbuf.append(c)

    def _esc_kdp(self, c, fsm):
        self._inbuf.append(~c)

    def _identify(self, c, fsm):  # report device
        self._fo.write(b"\x1b[?1;0c")

    def _endline(self, c, fsm):
        self._atendline = True
        self._inbuf.append(c)

    def _endprompt(self, c, fsm):
        self._atprompt = True
        self._inbuf.append(c)

    def _csidigitstart(self, c, fsm):
        fsm.push(c)

    def _csidigit(self, c, fsm):
        ns = fsm.pop()
        ns += c
        fsm.push(ns)

    def _csidigitdone(self, c, fsm):
        num = int(fsm.pop())
        fsm.pushalt(num)

    def _csireset(self, c, fsm):
        fsm.reset()

    def _sda(self, c, fsm):  # set display attribute, just reset
        fsm.reset()

    def _report(self, c, fsm):
        num = fsm.popalt()
        if num == 5:
            self._fo.write(b"\x1b[0n")  # report device OK
        elif num == 6:
            self._fo.write(b"\x1b[0;0R")  # report cursor position

    def _debug(self, c, fsm):
        print("DEBUG FSM: c: {!s} {}".format(c, fsm.current_state), file=sys.stderr)


if __name__ == "__main__":
    DATA = b"""\r
16:07:41 TEST BEGIN: arc4random_stress\r
16:07:41 PASS #1: pthread_create(&thr[i], ((void*)0), stress, ((void*)0)) == 0\r
16:07:44 TEST END: arc4random_stress\r
*** arc4random_stress ***\r
Result:       Pass\r
Time:         00:00:03\r
Pass count:   7\r
    """
    fo = ringbuffer.RingBuffer()  # Represents a pty or socket
    fo.write(DATA)
    term = Terminal(fo)
    inp = term.read(4096)
    assert len(DATA) == len(inp)
    assert inp == DATA

    CDATA = b"""\x1b[c\x1b[32mGreen\x1b[0m\r\n\x1b[31;01mBright Red\x1b[0m\r\n"""
    fo = ringbuffer.RingBuffer()
    fo.write(CDATA)
    term = Terminal(fo)
    inp = term.read(4096)
    EXP = b'Green\r\nBright Red\r\n'
    assert inp == EXP
    assert fo.read(4096) == b'\x1b[?1;0c'

    fo.write(b"text\r\n# ")
    inp = term.read_until_prompt()
    assert inp == b"text\r\n"

    fo = ringbuffer.RingBuffer()  # Represents a pty or socket
    fo.write(DATA)
    term = Terminal(fo)
    term.readline()
    line = term.readline()
    LINE = DATA.splitlines()[1] + b'\r\n'
    assert len(LINE) == len(line)
    assert line == LINE
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
