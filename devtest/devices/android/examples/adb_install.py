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
Demonstrate using the async installer.

    $ python3.6 -m devtest.devices.android.examples.adb_install <apkfile>
"""

import os
import sys
import signal

from devtest.devices.android import adb

from devtest.io import reactor
from devtest.io import streams


async def adb_install(serial, apkfile):
    ac = await adb.AsyncAndroidDeviceClient(serial)
    resp = await ac.install(apkfile)
    await ac.close()
    return resp


def main(argv):
    apkfile = argv[1]
    kern = reactor.get_kernel()
    return kern.run(adb_install, os.environ["ANDROID_SERIAL"], apkfile)


if __name__ == "__main__":
    sys.exit(not main(sys.argv))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
