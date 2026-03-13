"""Custom typing for objects commonly found within this framework.
"""

import os
from typing import Callable, Tuple, Union, Any, AnyStr
from socket import SocketType

from curio.io import Socket as AsyncSocket

from devtest.os.exitstatus import ExitStatus

AnySocket = Union[SocketType, AsyncSocket]

# Typically used for command lines as either full string or argv.
StringOrList = Union[str, list]
StringOrBytes = Union[str, bytes]
StringOrListOrTuple = Union[str, list, tuple]

# Outputs of runner types.
RunnerOut = Tuple[AnyStr, AnyStr, ExitStatus]
RunnerOutBytes = Tuple[bytes, bytes, ExitStatus]
RunnerOutStr = Tuple[str, str, ExitStatus]

# Command line runner callbacks. Checked types raise an exception on abnormal exit, returning only
# stdout on normal exit.  The others return (stdout, stderr, ExitStatus) tuple.
RunnerType = Callable[..., RunnerOut]
RunnerTypeBytes = Callable[..., RunnerOutBytes]
RunnerTypeStr = Callable[..., RunnerOutStr]
CheckedRunnerType = Callable[..., AnyStr]
CheckedRunnerTypeBytes = Callable[..., bytes]
CheckedRunnerTypeStr = Callable[..., str]

# Additional common types
AnyPath = Union[os.PathLike, str]
SignalHandler = Callable[[int, Any], None]
BytesReader = Callable[[AnyPath], bytes]
TextReader = Callable[[AnyPath], str]
BytesWriter = Callable[[AnyPath, bytes], int]
TextWriter = Callable[[AnyPath, str], int]
