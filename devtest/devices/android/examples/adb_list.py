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
Demonstrate using the async remote list.

    $ python3.6 -m devtest.devices.android.examples.adb_list <path>
"""

import os
import sys
import signal

from devtest.devices.android import adb

from devtest.io import reactor
from devtest.io import streams

out = streams.FileStream(sys.stdout.buffer)


async def printer(stat, name):
    await out.write(("{} {}\n".format(stat, name)).encode("utf-8"))


async def adb_list(serial, pathname):
    ac = await adb.AsyncAndroidDeviceClient(serial)
    st = await ac.stat(pathname)
    await out.write(("stat: {}\n".format(st)).encode("utf-8"))
    await ac.list(pathname, printer)
    await ac.close()


def main(argv):
    pathname = argv[1]
    kern = reactor.get_kernel()
    return kern.run(adb_list, os.environ["ANDROID_SERIAL"], pathname)


if __name__ == "__main__":
    sys.exit(not main(sys.argv))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
