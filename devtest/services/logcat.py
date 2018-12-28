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

"""
A logcat service for Android devices.

Will write a logcat capture file to the logdir_location.
"""

from devtest import logging
from devtest.qa import signals
from devtest.os import process
from . import Service


class LogcatService(Service):

    def __init__(self):
        super().__init__()
        self._inuse = {}
        signals.logdir_location.connect(self._set_logdir, weak=False)
        self._set_logdir(None, path="/var/tmp")

    def _set_logdir(self, runner, path=None):
        self._logdir = path

    def provide_for(self, needer):
        pm = process.get_manager()
        coproc = pm.coprocess()
        coproc.start(make_logcat_coroutine, needer.serno, self._logdir)
        self._inuse[needer.serno] = coproc

    def release_for(self, needer):
        coproc = self._inuse.pop(needer.serno, None)
        if coproc is not None:
            coproc.interrupt()
            coproc.wait()

    def close(self):
        signals.logdir_location.disconnect(self._set_logdir)


# Runs from coprocess server
def make_logcat_coroutine(serialno, logdir):
    import os
    import signal
    from devtest.io.reactor import spawn, SignalEvent
    from devtest.devices.android import adb

    logfilename = os.path.join(logdir, "logcat_{}.txt".format(serialno))
    aadc = adb.AsyncAndroidDeviceClient(serialno)

    async def dologcat(aadc, logfilename):
        await aadc.wait_for("device")
        try:
            signalset = SignalEvent(signal.SIGINT, signal.SIGTERM)
            try:
                with open(logfilename, "ab", 0) as logfile:
                    task = await spawn(aadc.logcat(logfile, logfile))
                    await signalset.wait()
                    await task.cancel()
            finally:
                await aadc.close()
        except KeyboardInterrupt:
            pass

    return dologcat(aadc, logfilename)


def initialize(manager):
    srv = LogcatService()
    manager.register(srv, "logcat")


def finalize(manager):
    srv = manager.unregister("logcat")
    srv.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
