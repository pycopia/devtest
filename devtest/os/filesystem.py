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
import stat


def df(path="/"):
    """Return file system blocks used and free, in bytes.

    Values are same as output of df command.

    Returns:
        tuple of used and free bytes on the given filesystem.
    """
    st = os.statvfs(path)
    return (((st.f_blocks - st.f_bfree) * st.f_bsize), (st.f_bavail * st.f_frsize))


def touch(path):
    """Update the atime and mtime of the file.

    If it doesn't exist, create it.
    """
    if os.path.exists(path):
        os.utime(path)
    else:
        open(path, "w").close()


class StatVfsResult:
    """Easier to use wrapper for os.statvfs_result.
    """

    def __init__(self, statvfs_result):
        self.statvfs_result = statvfs_result

    def __repr__(self):
        return f"{self.__class__.__name__}({self.statvfs_result!r})"

    def __getattr__(self, name):
        return getattr(self.statvfs_result, name)

    @property
    def size(self):
        """Size in bytes."""
        return self.statvfs_result.f_bsize * self.statvfs_result.f_blocks

    @property
    def available(self):
        """Available size in bytes."""
        return self.statvfs_result.f_bsize * self.statvfs_result.f_bavail

    @property
    def used(self):
        """Used size in bytes."""
        st = self.statvfs_result
        return (st.f_blocks - st.f_bavail) * st.f_bsize

    @property
    def percent_used(self):
        """Used size as percentage of total, including unavailable blocks."""
        st = self.statvfs_result
        return ((st.f_blocks - st.f_bavail) / st.f_blocks) * 100.0


class StatResult:
    """Easier to use wrapper for os.stat_result.
    """

    def __init__(self, stat_result):
        self.stat_result = stat_result

    def __repr__(self):
        return f"{self.__class__.__name__}({self.stat_result!r})"

    def __getattr__(self, name):
        return getattr(self.stat_result, name)

    @property
    def is_file(self):
        """Is a regular file?"""
        return stat.S_ISREG(self.stat_result.st_mode)

    @property
    def is_dir(self):
        """Is a directory?"""
        return stat.S_ISDIR(self.stat_result.st_mode)

    @property
    def is_char(self):
        """Is a character device?"""
        return stat.S_ISCHR(self.stat_result.st_mode)

    @property
    def is_block(self):
        """Is a block device?"""
        return stat.S_ISBLK(self.stat_result.st_mode)

    @property
    def is_fifo(self):
        """Is a FIFO (named pipe)?"""
        return stat.S_ISFIFO(self.stat_result.st_mode)

    @property
    def is_link(self):
        """Is a symbolic link?"""
        return stat.S_ISLNK(self.stat_result.st_mode)

    @property
    def is_sock(self):
        """Is a socket (unix)?"""
        return stat.S_ISSOCK(self.stat_result.st_mode)

    @property
    def is_executable(self):
        return bool(self.stat_result.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


if __name__ == "__main__":
    print(df())
