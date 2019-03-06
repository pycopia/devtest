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

"""Logcat utilities.

This framework interfaces to logcat in binary mode. These are tools to read binary logcat files.
"""

import sys
import os
import struct
import enum

from devtest.qa import signals


class LogPriority(enum.IntEnum):
    """Logging priority levels."""
    UNKNOWN = 0
    DEFAULT = 1
    VERBOSE = 2
    DEBUG = 3
    INFO = 4
    WARN = 5
    ERROR = 6
    FATAL = 7


class LogId(enum.IntEnum):
    """Source of the log entry.

    See: android/core/include/android/log.h
    """
    MAIN = 0
    RADIO = 1
    EVENTS = 2
    SYSTEM = 3
    CRASH = 4
    STATS = 5
    SECURITY = 6
    KERNEL = 7


class LogcatMessage:
    """An Android log message.

    Attributes:
        tag: (str) The tag of the message as set by the sender.
        priority: (LogPriority) The priority of the message.
        message: (str) The text message given by the caller.
        timestamp: (float) The devices' time that the message was created.
        pid: (int) The process ID of sending process.
        tid: (int) The thread ID of sending thread.
        lid: (int) The log ID.
        uid: (int) The user ID of the process that sent this message.
    """
    def __init__(self, pid, tid, sec, nsec, lid, uid, msg):
        self.pid = pid
        self.tid = tid
        self.timestamp = float(sec) + (nsec / 1e9)
        self.lid = LogId(lid)
        self.uid = uid
        try:
            self.priority = LogPriority(msg[0])
        except ValueError:
            self.priority = LogPriority.UNKNOWN
        tagend = msg.find(b'\x00')
        if tagend > 0:
            self.tag = (msg[1:tagend]).decode("ascii")
            self.message = (msg[tagend + 1:-1]).decode("utf8")
        else:
            self.tag = None
            self.message = msg.decode("utf8")

    def __str__(self):
        return "{:11.6f} {}:{} {}|{}¦{}".format(self.timestamp, self.pid, self.tid,
                                                self.tag, self.priority.name,
                                                self.message)


class LogcatFileReader:
    """Read and decode binary logcat files.

    These are usually obtained from a LogcatHandler dump_to.
    """
    LOGCAT_MESSAGE = struct.Struct("<HHiIIIII")  # logger_entry_v4

    def __init__(self, filename):
        self.filename = os.fspath(filename)

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self.filename)

    def search(self, tag=None, priority=None, regex=None):
        """Search the log for tag or regular expression in text.

        If tag is given, match on tag. If priority is also given, must match
        both tag and priority.
        IF a Regex object is given, match the message body only with that regex.
        If both tag and regex given, both must match. If all given, all must
        match.

        Yield LogcatMessage and MatchObject on matches. MatchObject will be None
        if regex is not given.
        """
        if tag is None and regex is None:
            raise ValueError("At least one of tag or regex must be supplied.")
        with open(self.filename, "rb") as lfo:
            self._sync_file(lfo)
            while True:
                lm = self._read_one(lfo)
                if lm is None:
                    break
                if tag and tag == lm.tag:
                    if priority is not None:
                        if lm.priority == priority:
                            if regex is not None:
                                mo = regex.search(lm.message)
                                if mo:
                                    yield lm, mo
                            else:
                                yield lm, None
                    else:
                        if regex is not None:
                            mo = regex.search(lm.message)
                            if mo:
                                yield lm, mo
                        else:
                            yield lm, None
                if regex is not None:
                    mo = regex.search(lm.message)
                    if mo:
                        yield lm, mo

    def find_first_tag(self, tag):
        """Find first occurence of a tag.
        """
        for lm, _ in self.search(tag=tag):
            return lm

    def dump(self, tag=None):
        """Write deocded log to stdout."""
        return self.dump_to(sys.stdout.buffer, tag=tag)

    def dump_to(self, fo, tag=None):
        """Dump decoded text to a file-like object."""
        with open(self.filename, "rb") as lfo:
            self._sync_file(lfo)
            lines = self._dump(lfo, fo, tag)
        return lines

    def _dump(self, fo, out, tag):
        lines = 0
        try:
            while True:
                lm = self._read_one(fo)
                if lm is None:
                    break
                if tag and tag != lm.tag:
                    continue
                lines += 1
                out.write(str(lm).encode("utf8"))
                out.write(b'\n')
        except BrokenPipeError:
            pass
        return lines

    def dump_to_file(self, localfile, tag=None):
        with open(localfile, "wb") as fo:
            lines = self.dump_to(fo, tag)
        return lines

    def _read_one(self, fo):
        s = self.LOGCAT_MESSAGE
        rawhdr = fo.read(s.size)
        if len(rawhdr) < s.size:
            return None
        payload_len, hdr_size, pid, tid, sec, nsec, lid, uid = s.unpack(rawhdr)
        payload = fo.read(payload_len)
        return LogcatMessage(pid, tid, sec, nsec, lid, uid, payload)

    def _sync_file(self, fo):
        # in case of cruft at start of file.
        # The header size is fixed, so will always have the same value, and
        # hdr_size field equals LOGCAT_MESSAGE size. Look for that.
        header_peek = struct.Struct("<HH")
        while True:
            payload_len, hdr_size = header_peek.unpack(fo.read(header_peek.size))
            if hdr_size == self.LOGCAT_MESSAGE.size:
                fo.seek(-header_peek.size, 1)
                return
            else:
                fo.seek(-(header_peek.size - 1), 1)


def to_logcat_filereader(analyzer, data=None, config=None):
    """Data converter handler."""
    if isinstance(data, dict):
        fname = data.get("logcatfile")
        if fname:
            fname = analyzer.fix_path(fname)
            return LogcatFileReader(fname)


signals.data_convert.connect(to_logcat_filereader)


if __name__ == "__main__":
    fname = sys.argv[1] if len(sys.argv) > 1 else None
    tag = sys.argv[2] if len(sys.argv) > 2 else None
    if fname:
        lfr = LogcatFileReader(fname)
        lfr.dump(tag=tag)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
