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
Run programs with elevated privileges using sudo.
"""

from __future__ import generator_stop

from devtest.os import procutils

from . import process

SUDO = procutils.which("sudo")
if SUDO is None:
    raise ImportError("This module will not work without 'sudo' in PATH")


def sudo(command, user=None, password=None, extraopts=None):
    """Build an sudo command line and return an active subprocess.

    Optionally supply a user and password, if required.
    """
    opts = "-S {}".format("-u {}".format(user) if user else "")
    cmd = "{} {} {} {}".format(SUDO, opts, extraopts or "", command)
    proc = process.start_process(cmd, delaytime=0.5)
    if password:
        process.run_coroutine(proc.stderr.read(9))  # discard password prompt
        process.run_coroutine(proc.stdout.write("{}\r".format(password)))
        process.run_coroutine(proc.stderr.read(1))  # discard newline
    return proc


def sudo_reset():
    cmd = "{} -k".format(SUDO)
    return process.run_command(cmd, delaytime=0.5)


def sudo_command(cmd, user=None, password=None, extraopts=None):
    """Run a command with sudo and return the output, a tuple of (stdout,
    stderr).
    """
    proc = sudo(cmd, user=user, password=password, extraopts=extraopts)
    return process.run_process(proc)


def _test(argv):
    # only works if sudo does not require a password
    outlines, err = sudo_command("id -u")
    print("id outlines", outlines)
    print("id errout", err)
    assert int(outlines[0]) == 0, "Didn't get root UID"


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
