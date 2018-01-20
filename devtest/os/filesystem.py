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
