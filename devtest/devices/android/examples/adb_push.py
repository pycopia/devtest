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
Demonstrate using adb push.

    $ python3.6 -m devtest.devices.android.examples.adb_push <localpath>... <remotepath>
"""

import os
import sys

from devtest.devices.android import adb

from devtest.io import reactor


async def adb_push(serial, localfiles, remotepath):
    ac = await adb.AsyncAndroidDeviceClient(serial)
    await ac.push(localfiles, remotepath)
    await ac.close()
    return 0


def main(argv):
    if len(argv) >= 3:
        localpaths = argv[1:-1]
        remotepath = argv[-1]
        kern = reactor.get_new_kernel(debug=True)
        return kern.run(adb_push,
                        os.environ["ANDROID_SERIAL"],
                        localpaths,
                        remotepath,
                        shutdown=True)
    else:
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
