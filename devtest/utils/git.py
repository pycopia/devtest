"""
Function that interface to git.
"""

import os
import re
import subprocess


BLAME_CMD = "git -C {cwd} blame -L {lineno},{lineno} -tp {fname}"


def git_blame(filename, lineno):
    """Find out the last person to commit a line of code.

    Provide the file name and line number, starting from 1, in the file.

    Returns a tuple of (Real Name, and Email Address).
    """
    filename = os.path.expanduser(filename)
    cmd = BLAME_CMD.format(lineno=lineno, fname=filename, cwd=os.path.dirname(filename))
    text = subprocess.check_output(cmd.split(), shell=False)
    return re.search(r"^author (.*)$\s*^author-mail (.*)$", text.decode("utf-8"), re.M).groups()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
