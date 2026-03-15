"""Controller for accessing the host running the test, itself.

Provides a consistent interface for local host and remote hosts.
"""

import os
import re
import fnmatch
from typing import Union, Optional, Generator, Tuple, cast

from devtest.os import process
from devtest.os import filesystem
from devtest.devices import hostcontroller


class SelfControllerError(hostcontroller.HostControllerError):
    """Raised on errors in SelfController."""


class SelfController(hostcontroller.LinuxController):
    """Controller interface for local host, the host running this. Usually the test runner.

    Provides an interface for performing operations on the local host that is consistent with
    remote devices.
    """

    def _run_command(self, command, input, use_pty, timeout, environment):
        return process.run_command(command, input=input, timeout=timeout)

    def _read_file(self, path: Union[os.PathLike, str],
                   encoding: Optional[str]) -> Union[str, bytes]:
        try:
            with open(path, "rb") as fo:
                out = fo.read()
        except OSError as oserr:
            raise SelfControllerError(f"Failed to read: {path}") from oserr
        if encoding is None:
            return cast(bytes, out)
        else:
            return cast(str, out.decode(encoding))

    def _write_file(self,
                    path: Union[os.PathLike, str],
                    data: Union[str, bytes],
                    encoding: Optional[str],
                    permissions: Optional[int] = None) -> int:
        try:
            with open(path, "wb") as fo:
                if encoding is None:
                    writ = fo.write(cast(bytes, data))
                else:
                    data = cast(str, data)
                    writ = fo.write(data.encode(encoding))
        except OSError as oserr:
            raise SelfControllerError(f"Failed to write: {path}") from oserr
        if permissions is not None:
            os.chmod(path, permissions)
        return writ

    def unlink(self, path: Union[os.PathLike, str]):
        """Unlink (delete) the path to a file.
        """
        return os.unlink(str(path))

    def rename(self, src: Union[os.PathLike, str], dst: Union[os.PathLike, str]):
        """Rename a file from source path to dest path.
        """
        return os.rename(str(src), str(dst))

    def listdir(self,
                path: Union[os.PathLike, str],
                glob: Optional[str] = None,
                encoding: str = "utf8") -> Generator[Tuple[str, filesystem.StatResult], None, None]:
        """Iterator that lists a directory on local host.

        Yields:
            name and StatResult.
        """
        regex = re.compile(fnmatch.translate(glob)) if glob else None
        for entry in os.scandir(str(path)):
            if regex is not None and not regex.match(entry.name):
                continue
            try:
                yield entry.name, filesystem.StatResult(entry.stat())
            except FileNotFoundError:  # dangling symlink
                continue
