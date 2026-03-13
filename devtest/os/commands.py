"""Support for running system commands in a standardized way for different runners.

May be used for both local and remote invocations.

A Command object encapsulates a particular command invocation and how to parse the output of
that invocation into a common object.
"""

import abc
import os
import subprocess
from typing import Callable, List, Any

from devtest.textutils import shparser
from devtest.os import filesystem


class CommandUsageError(Exception):
    """Raised if command cannot be formatted with provided arguments."""


class Command(abc.ABC):
    """Base class for running commands and getting structured output.

    Set CMD class attribute in your subclass, and define the `parse` method.
    """
    CMD = "echo {}"

    def __init__(self, *args):
        try:
            self._command = self.__class__.CMD.format(*args)
        except IndexError:
            raise CommandUsageError(f"Can't format {self.CMD!r} with args {args!r}") from None
        self._argv = shparser.split(self._command)

    @property
    def command(self) -> str:
        """Command to execute, as a string."""
        return self._command

    @property
    def argv(self) -> List[str]:
        """Command to execute, in argv form."""
        return self._argv

    def run(self) -> Any:
        """Run command here and now.

        Returns:
            The object that the `parse` method returns.
        """
        outobj = subprocess.run(self._argv, stdout=subprocess.PIPE)
        return self.parse(outobj.stdout.decode("ascii"))

    def run_with(self, runner: Callable[[str], str]) -> Any:
        """Pass command to runner and return parsed output.
        """
        out = runner(self._command)
        return self.parse(out)

    def run_with_argv(self, runner: Callable[[List], str]) -> Any:
        """Pass command to runner with argument vector, and return parsed output.
        """
        out = runner(self._argv)
        return self.parse(out)

    @abc.abstractmethod
    def parse(self, output: str) -> Any:
        """Parse the output of `command`, returning some object."""
        pass


class StatVfs(Command):
    """Get a StatVfsResult object from the statvfs function.
    """
    CMD = "stat -f -c '%s %S %b %f %a %c %d %l' {}"

    def parse(self, output: str) -> filesystem.StatVfsResult:
        statvalues = [int(s) for s in output.split()]
        # Adjust for different ordering of values in statvfs structure.
        statvalues.insert(7, statvalues[6])  # ffree is the same as favail
        statvalues.insert(8, 0)  # f_flag unavailable from stat command
        return filesystem.StatVfsResult(os.statvfs_result(statvalues))


class Stat(Command):
    """Get a StatResult object from the stat command.

    Use this to get the metadata about a file or directory.
    """
    CMD = 'stat --format="%f %i %d %h %u %g %s %X %Y %Z" {}'

    def parse(self, output: str) -> filesystem.StatResult:
        statvalues = []
        # The mode (%f) is output as hex, the rest decimal.
        parts = output.split()
        statvalues.append(int(parts[0], 16))
        statvalues.extend(int(part) for part in parts[1:])
        return filesystem.StatResult(os.stat_result(statvalues))


if __name__ == "__main__":
    st_root = StatVfs("/").run()
    print("root dir:", st_root)
    print("percent?", st_root.percent_used)

    st_hosts = Stat("/etc/hosts").run()
    print("hosts file:", st_hosts)
    print("executable?", st_hosts.is_executable)
    print("is dir?", st_hosts.is_dir)
    assert not st_hosts.is_dir
    assert st_hosts.is_file
    assert not st_hosts.is_executable

    st_stat = Stat("/usr/bin/stat").run()
    print("stat cmd:", st_stat)
    print("executable?", st_stat.is_executable)
    assert st_stat.is_file
    assert st_stat.is_executable
    assert not st_stat.is_dir

    st_homedir = Stat(os.path.expandvars("$HOME")).run()
    print("HOME dir:", st_homedir)
    print("executable?", st_homedir.is_executable)
    print("is dir?", st_homedir.is_dir)
    assert st_homedir.is_dir
