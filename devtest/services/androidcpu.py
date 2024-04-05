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
"""Monitor CPU usage of a process on Android.
"""

from devtest.os import process
from . import Service


class CPUMonitorService(Service):

    def __init__(self):
        super().__init__()
        self._inuse = {}

    def provide_for(self, needer, **kwargs):
        pid = kwargs.get("pid")
        interval = kwargs.get("interval", 1)
        if not pid:
            return False
        if (needer.serno, pid) in self._inuse:
            return True
        pm = process.get_manager()
        coproc = pm.coprocess()
        coproc.start(make_cpu_monitor, needer.serno, pid, interval)
        self._inuse[(needer.serno, pid)] = coproc
        return True

    def release_for(self, needer, **kwargs):
        pid = kwargs.get("pid")
        if not pid:
            return
        result = None
        coproc = self._inuse.pop((needer.serno, pid), None)
        if coproc is not None:
            coproc.terminate()
            result = coproc.wait()
            coproc.close()
        return result

    def close(self):
        while self._inuse:
            (serno, pid), proc = self._inuse.popitem()
            proc.interrupt()
            proc.wait()


# Runs from coprocess server
def make_cpu_monitor(serialno, pid, interval):
    import io
    import signal
    from devtest.os import cpuinfo
    from devtest.io.reactor import sleep, spawn, SignalEvent
    from devtest.devices.android import adb

    class LocalCPUMonitor:

        def __init__(self, adbclient, pid, interval):
            self._adb = adbclient
            self._pid = pid
            self._path = "/proc/{pid:d}/stat".format(pid=pid)
            self._interval = float(interval)
            self._start_jiffies = None
            self._starttime = None

        async def get_timestamp(self):
            with io.BytesIO() as bio:
                await self._adb.pull_file("/proc/uptime", bio)
                text = bio.getvalue()
            # Wall clock since boot, combined idle time of all cpus
            clock, _ = text.split()
            return float(clock)

        async def get_procstat(self):
            with io.BytesIO() as bio:
                await self._adb.pull_file(self._path, bio)
                ps = cpuinfo.ProcStat.from_text(bio.getvalue())
            return ps

        async def get_current(self):
            now = await self.get_timestamp()
            ps = await self.get_procstat()
            current_jiffies = ps.stime + ps.utime
            return now, float(current_jiffies - self._start_jiffies) / (now - self._starttime)

        async def run(self, accumulator):
            self._starttime = await self.get_timestamp()
            ps = await self.get_procstat()
            self._start_jiffies = ps.stime + ps.utime
            while True:
                await sleep(self._interval)
                timestamp, utilization = await self.get_current()
                accumulator.append((timestamp - self._starttime, utilization))

    async def docpumonitor(serialno, pid, interval):
        cpudata = []
        aadc = await adb.AsyncAndroidDeviceClient(serialno)
        await aadc.wait_for("device")
        cpumon = LocalCPUMonitor(aadc, pid, interval)
        try:
            signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
            try:
                task = await spawn(cpumon.run(cpudata))
                await signalset.wait()
                await task.cancel()
            finally:
                del cpumon
                await aadc.close()
        except KeyboardInterrupt:
            pass
        return cpudata

    return docpumonitor(serialno, pid, interval)


def initialize(manager):
    srv = CPUMonitorService()
    manager.register(srv, "androidcpu")


def finalize(manager):
    srv = manager.unregister("androidcpu")
    srv.close()


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
