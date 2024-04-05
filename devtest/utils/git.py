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
