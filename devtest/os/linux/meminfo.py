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

"""Information about process memory usage.
"""

import os
import pathlib
from collections import namedtuple, defaultdict


class VmFlags:
    def __init__(self, flags):
        self._flags = flags  # TODO break out flags to attributes

    def __repr__(self):
        return "VmFlags({!r})".format(self._flags)

    @property
    def flags(self):
        return self._flags

    @classmethod
    def from_string(cls, bytestring):
        return cls(bytestring.decode("ascii"))


MemUsage = namedtuple("MemUsage",
                      ["Size", "KernelPageSize", "MMUPageSize", "Rss", "Pss",
                       "Uss", "Shared_Clean", "Shared_Dirty", "Private_Clean",
                       "Private_Dirty", "Referenced", "Anonymous", "LazyFree",
                       "AnonHugePages", "ShmemPmdMapped", "Shared_Hugetlb",
                       "Private_Hugetlb", "Swap", "SwapPss", "Locked",
                       "VmFlags"])


class VirtualMemoryArea:
    """A memory mapped area of a process.

    Attributes:
        name: str
        start: int
        end: int
        offset: int
        perms: str
        device: str
        inode: int
        usage: MemUsage

    The permissions are:
        r = read
        w = write
        x = execute
        s = shared
        p = private (copy on write)
    """

    def __init__(self, name: str, start: int, end: int, offset: int, perms: str,
                 device: str, inode: int, usage: MemUsage = None):
        self.name = name
        self.start = start
        self.end = end
        self.offset = offset
        self.perms = perms
        self.device = device
        self.inode = inode
        self._usage = usage

    def __str__(self):
        return "{:16x}-{:16x} {} {:16x} {} {} {}".format(
            self.start, self.end, self.perms, self.offset,
            self.device, self.inode,
            self.name if self.name is not None else "")

    @property
    def usage(self):
        return self._usage

    @usage.setter
    def usage(self, newusage):
        if isinstance(newusage, MemUsage):
            self._usage = newusage
        else:
            raise ValueError("usage should be MemUsage")

    @classmethod
    def from_line(cls, bytestring):
        # address perms offset dev inode name
        # 55d60111e000-55d601126000 r-xp 00000000 fd:03 389921   /bin/cat
        parts = bytestring.split()
        start_s, _, end_s = parts[0].partition(b"-")
        name = parts[-1] if len(parts) > 5 else None
        if name is not None:
            if name.startswith(b"/"):
                name = pathlib.Path(name.decode("ascii"))
            else:
                name = name.decode("ascii")
        return cls(name, int(start_s, 16), int(end_s, 16), int(parts[2], 16),
                   (parts[1]).decode("ascii"),
                   (parts[3]).decode("ascii"), int(parts[4]))


class Maps(list):

    SMAPS = "/proc/{pid}/smaps"

    @classmethod
    def from_text(cls, bytesblob):
        units = {b"kB": 1024}
        currentvma = None
        currentusage = {}
        me = cls()
        for line in bytesblob.splitlines():
            if line[0] in b'0123456789abcdef' and b'-' in line:
                if currentvma is not None:
                    currentusage["Uss"] = (currentusage["Private_Clean"] +
                                           currentusage["Private_Dirty"])
                    currentvma.usage = MemUsage(**currentusage)
                    currentusage = {}
                vma = VirtualMemoryArea.from_line(line)
                currentvma = vma
                me.append(vma)
            elif line[0] >= 65 and line[0] <= 90:  # A-Z
                # Size:                 32 kB
                # VmFlags: rd ex mr mw me dw sd
                name, rest = line.split(b':')
                if name == b'VmFlags':
                    currentusage["VmFlags"] = VmFlags.from_string(rest.strip())
                else:
                    val, unit = rest.split()
                    val = int(val) * units[unit]
                    currentusage[name.decode("ascii")] = val
        if currentvma is not None:
            currentusage["Uss"] = (currentusage["Private_Clean"] +
                                   currentusage["Private_Dirty"])
            currentvma.usage = MemUsage(**currentusage)
        return me

    @classmethod
    def from_pid(cls, pid):
        mapfile = Maps.SMAPS.format(pid=pid)
        with open(mapfile, "rb") as fo:
            text = fo.read()
        return cls.from_text(text)

    @classmethod
    def from_main(cls):
        return cls.from_pid(os.getpid())

    def rollup(self):
        acc = defaultdict(int)
        for vma in self:
            usage = vma.usage
            acc["Size"] += usage.Size
            acc["Rss"] += usage.Rss
            acc["Pss"] += usage.Pss
            acc["Uss"] += usage.Uss
            acc["Shared_Clean"] += usage.Shared_Clean
            acc["Shared_Dirty"] += usage.Shared_Dirty
            acc["Private_Clean"] += usage.Private_Clean
            acc["Private_Dirty"] += usage.Private_Dirty
            acc["Referenced"] += usage.Referenced
            acc["Anonymous"] += usage.Anonymous
            acc["LazyFree"] += usage.LazyFree
            acc["AnonHugePages"] += usage.AnonHugePages
            acc["ShmemPmdMapped"] += usage.ShmemPmdMapped
            acc["Shared_Hugetlb"] += usage.Shared_Hugetlb
            acc["Private_Hugetlb"] += usage.Private_Hugetlb
            acc["Swap"] += usage.Swap
            acc["SwapPss"] += usage.SwapPss
            acc["Locked"] += usage.Locked
        acc["KernelPageSize"] = vma.usage.KernelPageSize
        acc["MMUPageSize"] = vma.usage.MMUPageSize
        acc["VmFlags"] = None
        return MemUsage(**acc)


class MemoryMonitor:
    """Aid monitoring memory usage of a process over a span of time.

    Call start method, wait some time, then call the stop method.
    Use the difference method to get a MemUsage with fields set to the
    difference of the stop and start values.
    """

    CLEAR_REFS = "/proc/{pid}/clear_refs"

    def __init__(self, pid=None):
        if pid is None:
            pid = os.getpid()
        self._pid = pid
        self._startmap = None
        self._stopmap = None

    def start(self):
        self._startmap = Maps.from_pid(self._pid)
        self._stopmap = None
        with open(MemoryMonitor.CLEAR_REFS.format(pid=self._pid), "wb") as fo:
            fo.write(b"1\n")

    def current(self):
        return Maps.from_pid(self._pid)

    def stop(self):
        if self._startmap is None:
            raise RuntimeError("Stopping memory monitor before starting.")
        self._stopmap = Maps.from_pid(self._pid)

    def difference(self):
        if self._startmap is None or self._stopmap is None:
            raise RuntimeError("MemoryMonitor was not run.")
        new = {"VmFlags": None}
        memstop = self._stopmap.rollup()._asdict()
        memstart = self._startmap.rollup()._asdict()
        for fname in MemUsage._fields:
            if fname == "VmFlags":
                continue
            new[fname] = memstop[fname] - memstart[fname]
        return MemUsage(**new)

    def referenced_pages(self):
        """return number of pages referenced during the time span.
        """
        if self._stopmap is None:
            raise RuntimeError("MemoryMonitor was not run.")
        memstop = self._stopmap.rollup()
        return memstop.Referenced // memstop.KernelPageSize


if __name__ == "__main__":
    import time
    import sys

    m = Maps.from_main()
    for vma in m:
        print(vma)
    total = m.rollup()
    print(total)
    print(total.Uss, total.Referenced)

    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    mon = MemoryMonitor(pid)
    mon.start()
    print("Memory monitor started.")
    for i in range(10):
        time.sleep(1)
        print("Uss:", mon.current().rollup().Uss)
    mon.stop()
    print("Memory monitor stopped.")
    diff = mon.difference()
    print("Change is Uss:", diff.Uss)
    print("Referenced pages:", mon.referenced_pages())

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
