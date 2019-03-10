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

"""Monitor memory usage of a process on Android.
"""

from devtest.os import process
from . import Service


class MemoryMonitorService(Service):

    def __init__(self):
        super().__init__()
        self._inuse = {}

    def provide_for(self, needer, **kwargs):
        pid = kwargs.get("pid")
        interval = kwargs.get("interval", 1)
        if not pid:
            return
        if (needer.serno, pid) in self._inuse:
            return
        pm = process.get_manager()
        coproc = pm.coprocess()
        coproc.start(make_memory_monitor, needer.serno, pid, interval)
        self._inuse[(needer.serno, pid)] = coproc

    def release_for(self, needer, **kwargs):
        pid = kwargs.get("pid")
        if not pid:
            return
        result = None
        coproc = self._inuse.pop((needer.serno, pid), None)
        if coproc is not None:
            coproc.interrupt()
            result = coproc.wait()
        return result

    def close(self):
        while self._inuse:
            (serno, pid), proc = self._inuse.popitem()
            proc.interrupt()
            proc.wait()


# Runs from coprocess server
def make_memory_monitor(serialno, pid, interval):
    import io
    import signal
    from datetime import datetime, timezone
    from devtest.os import meminfo
    from devtest.io.reactor import sleep, spawn, SignalEvent
    from devtest.devices.android import adb

    class LocalMemoryMonitor:

        def __init__(self, adbclient, pid, interval):
            self._adb = adbclient
            self._path = meminfo.Maps.SMAPS.format(pid=pid)
            self._interval = float(interval)

        async def get_current(self):
            with io.BytesIO() as bio:
                await self._adb.pull_file(self._path, bio)
                text = bio.getvalue()
            return meminfo.Maps.from_text(text)

        async def run(self, accumulator):
            while True:
                timestamp = datetime.now(tz=timezone.utc)
                mi = await self.get_current()
                accumulator.append((timestamp, mi.rollup()))
                await sleep(self._interval)

    async def domemorymonitor(serialno, pid, interval):
        memdata = []
        aadc = await adb.AsyncAndroidDeviceClient(serialno)
        await aadc.wait_for("device")
        mm = LocalMemoryMonitor(aadc, pid, interval)
        try:
            signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
            try:
                task = await spawn(mm.run(memdata))
                await signalset.wait()
                await task.cancel()
            finally:
                del mm
                await aadc.close()
        except KeyboardInterrupt:
            pass
        return memdata

    return domemorymonitor(serialno, pid, interval)


def initialize(manager):
    srv = MemoryMonitorService()
    manager.register(srv, "androidmemory")


def finalize(manager):
    srv = manager.unregister("androidmemory")
    srv.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
