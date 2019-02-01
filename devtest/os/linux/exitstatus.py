# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import signal


class ExitStatus:
    """Common exit status object for subprocesses and devices.

    Can be avaluated for truthiness and will avaluate True only if status
    indicates a normal process exit. A normal exit is zero, but this will still
    evaluate True. It works the same as a typical posix shell.
    """
    EXITED = 1
    STOPPED = 2
    SIGNALED = 3

    def __init__(self, sts, name="unknown", returncode=None):
        """Common exit status object.

        Args:
            sts: raw status value from OS.
            name: name of the process to report when stringified.
            returncode: optional, pre-cooked returncode from subprocess module.
                        overrides sts if used.
        """
        self.name = name
        if returncode is not None:
            if returncode < 0:
                self.state = 3
                self._status = self._signal = -returncode
            else:
                self.state = 1
                self._status = returncode
                self._signal = 0
            return
        if os.WIFEXITED(sts):
            self.state = 1
            self._status = os.WEXITSTATUS(sts)
            self._signal = 0

        elif os.WIFSTOPPED(sts):
            self.state = 2
            self._status = self._signal = os.WSTOPSIG(sts)

        elif os.WIFSIGNALED(sts):
            self.state = 3
            self._status = self._signal = os.WTERMSIG(sts)

    @property
    def status(self):
        return self._status

    @property
    def signal(self):
        return signal.Signals(self._signal)

    def exited(self):
        return self.state == 1

    def stopped(self):
        return self.state == 2

    def signalled(self):
        return self.state == 3

    def __int__(self):
        return self._status

    # exit status truth value is True if normal exit, and False otherwise.
    def __bool__(self):
        return (self.state == 1) and not self._status

    def __str__(self):
        if self.state == 1:
            if self._status == 0:
                return "{}: Exited normally.".format(self.name)
            else:
                return "{}: Exited abnormally with status {:d}.".format(
                    self.name, self._status)
        elif self.state == 2:
            return "{} is stopped by signal {:d}.".format(
                self.name, self._signal)
        elif self.state == 3:
            return "{} exited by signal {:d}. ".format(
                self.name, self.signal)
        else:
            raise RuntimeError("FIXME! unknown state in ExitStatus")


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
