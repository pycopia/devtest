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
Demonstrate using the async spawn to copy a stream of events to a stdout.

Could be modified to write to any file, or read another input event node.

Run as:

    $ python3.6 -m devtest.devices.android.examples.adb_events
"""

import os
import sys
import signal

from devtest.devices.android import adb

from devtest.io import reactor
from devtest.io import streams


async def adb_events(serial):
    ac = await adb.AsyncAndroidDeviceClient(serial)
    p = await ac.spawn(['getevent', '-t', '/dev/input/event3'])

    try:
        signalset = reactor.SignalEvent(signal.SIGINT, signal.SIGTERM)
        try:
            task = await reactor.spawn(p.copy_to(streams.FileStream(sys.stdout.buffer)))
            await signalset.wait()
            await task.cancel()
        finally:
            await p.close()
            await ac.close()
    except KeyboardInterrupt:
        pass


def main(argv):
    kern = reactor.get_kernel()
    kern.run(adb_events, os.environ["ANDROID_SERIAL"])


if __name__ == "__main__":
    main(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
