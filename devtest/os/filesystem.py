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
File system utilities.
"""

import os


def df(path="/"):
    """Return file system blocks used and free.

    Values are same as output of df command.
    """
    stat = os.statvfs(path)
    return (((stat.f_blocks - stat.f_bfree) * 8),
            (stat.f_bavail * (stat.f_frsize // 512)))


def touch(path):
    """Update the atime and mtime of the file.

    If it doesn't exist, create it.
    """
    if os.path.exists(path):
        os.utime(path)
    else:
        open(path, "w").close()


if __name__ == "__main__":
    print(df())

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
