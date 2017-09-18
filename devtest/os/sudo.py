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
        process.run_coroutine(proc.stderr.read(9)) # discard password prompt
        process.run_coroutine(proc.stdout.write("{}\r".format(password)))
        process.run_coroutine(proc.stderr.read(1)) # discard newline
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
