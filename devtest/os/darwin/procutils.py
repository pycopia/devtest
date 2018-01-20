#!/usr/bin/python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Process utilities.
"""

import os

from devtest.os.exitstatus import ExitStatus


def run_as(pwent, umask=0o22):
    """Drop privileges to given user's password entry, and set up
    environment. Assumes the parent process has root privileges.
    """
    os.umask(umask)
    home = pwent.home
    try:
        os.chdir(home)
    except OSError:
        os.chdir("/")
    # drop privs to user
    os.setgroups(pwent.groups)
    os.setgid(pwent.gid)
    os.setegid(pwent.gid)
    os.setuid(pwent.uid)
    os.seteuid(pwent.uid)
    os.environ["HOME"] = home
    os.environ["USER"] = pwent.name
    os.environ["LOGNAME"] = pwent.name
    os.environ["SHELL"] = pwent.shell
    os.environ["PATH"] = "/bin:/usr/bin:/usr/local/bin"


def system(cmd):
    """Like os.system(), except returns ExitStatus object."""
    sts = os.system(cmd)
    return ExitStatus(sts, name=cmd.split()[0])


def which(basename):
    """Returns the fully qualified path name (by searching PATH) of the given
    program name.
    """
    if "/" in basename:
        if os.access(basename, os.F_OK | os.X_OK):
            return basename
        else:
            return None
    for pe in os.environ["PATH"].split(os.pathsep):
        testname = os.path.join(pe, basename)
        if os.access(testname, os.F_OK | os.X_OK):
            return testname
    return None

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
