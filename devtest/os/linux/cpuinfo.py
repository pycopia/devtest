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

"""CPU information and monitors.
"""

import re
import time
import typing


_ALLNUMBERS_RE = re.compile(rb'(\d+)(?(1)[ \n]|\(.*\))')


class ProcStat(typing.NamedTuple):
    """Process status.

    From /proc/PID/stat, with a few fields elided.
    """
    pid: int  # process id
    ppid: int  # process id of the parent process
    pgrp: int  # pgrp of the process
    sid: int  # session id
    tty_nr: int  # tty the process uses
    tty_pgrp: int  # pgrp of the tty
    flags: int  # task flags
    min_flt: int  # number of minor faults
    cmin_flt: int  # number of minor faults with child's
    maj_flt: int  # number of major faults
    cmaj_flt: int  # number of major faults with child's
    utime: int  # user mode jiffies
    stime: int  # kernel mode jiffies
    cutime: int  # user mode jiffies with child's
    cstime: int  # kernel mode jiffies with child's
    priority: int  # priority level
    nice: int  # nice level
    num_threads: int  # number of threads
    it_real_value: int  # (obsolete, always 0)
    start_time: int  # time the process started after system boot
    vsize: int  # virtual memory size
    rss: int  # resident set memory size
    rsslim: int  # current limit in bytes on the rss
    start_code: int  # address above which program text can run
    end_code: int  # address below which program text can run
    start_stack: int  # address of the start of the main process stack
    esp: int  # current value of ESP
    eip: int  # current value of EIP
    pending: int  # bitmap of pending signals
    blocked: int  # bitmap of blocked signals
    sigign: int  # bitmap of ignored signals
    sigcatch: int  # bitmap of caught signals
    has_wchan: int  # Boolean, Has a /proc/PID/wchan entry
    exit_signal: int  # signal to send to parent thread on exit
    task_cpu: int  # which CPU the task is scheduled on
    rt_priority: int  # realtime priority
    policy: int  # scheduling policy (man sched_setscheduler)
    blkio_ticks: int  # time spent waiting for block IO
    gtime: int  # guest time of the task in jiffies
    cgtime: int  # guest time of the task children in jiffies
    start_data: int  # address above which program data+bss is placed
    end_data: int  # address below which program data+bss is placed
    start_brk: int  # address above which program heap can be expanded with brk()
    arg_start: int  # address above which program command line is placed
    arg_end: int  # address below which program command line is placed
    env_start: int  # address above which program environment is placed
    env_end: int  # address below which program environment is placed
    exit_code: int  # the thread's exit_code in the form reported by the waitpid system call

    @classmethod
    def from_text(cls, bytesblob):
        res = [int(s) for s in _ALLNUMBERS_RE.findall(bytesblob)]
        # remove the unused entries
        assert res[33] == 0 and res[34] == 0
        del res[33]
        del res[34]
        return cls(*res)

    @classmethod
    def from_pid(cls, pid):
        fname = "/proc/{pid:d}/stat".format(pid=pid)
        with open(fname, "rb") as fo:
            text = fo.read()
        return cls.from_text(text)


class CPUUtilizationMonitor:
    """Helper to measure CPU utilization of a process."""
    def __init__(self, pid: int):
        self.pid = int(pid)
        self._starttime = None
        self._start_tics = None

    def start(self):
        """Start monitor by recording current state.
        """
        self._starttime = time.time()
        ps = ProcStat.from_pid(self.pid)
        self._start_tics = ps.stime + ps.utime

    def current(self):
        """Current CPU utilization.

        Returns:
            Utilization since start called, float percent.
        """
        ps = ProcStat.from_pid(self.pid)
        now = time.time()
        tics = ps.stime + ps.utime
        return float(tics - self._start_tics) / (now - self._starttime)

    def elapsed(self):
        """Time since start of monitoring.

        Return:
            elapsed time in seconds, as float.
        """
        return time.time() - self._startime

    def end(self):
        """Stop monitor.

        Returns:
            Elapsed time of run, in seconds (float).
        """
        st = self._starttime
        self._starttime = None
        self._start_tics = None
        return time.time() - st


if __name__ == "__main__":
    import os
    ps = ProcStat.from_pid(os.getpid())
    mon = CPUUtilizationMonitor(os.getpid())
    mon.start()
    time.sleep(2.9)
    for i in range(10000000):
        x = i ** 2
    print(mon.current())
    mon.end()
    del mon
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
