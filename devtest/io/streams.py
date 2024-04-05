# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""IO for streams.

Use the Stream object from here. Collects the curio supplies Stream objects and
adds some new ones.
"""

from __future__ import generator_stop

from curio.traps import _read_wait  # noqa
from curio.io import StreamBase, FileStream, SocketStream, Socket, WantRead, WantWrite  # noqa
from curio.channel import Connection, Channel  # noqa

__all__ = ["ReadableStream", "FileStream", "SocketStream", "Connection", "Channel"]


class ReadableStream(StreamBase):
    """Stream wrapper for an object with read-only file descriptor.
    """

    async def _read(self, maxbytes=-1):
        while True:
            try:
                return self._file.read(maxbytes)
            except WantRead:
                await _read_wait(self._fileno)


def _test(argv):
    from . import reactor

    async def user2err(inp, outp):
        async for line in inp:
            if line.startswith(b"Q"):
                break
            await outp.write(line)
            await outp.flush()

    inp = FileStream(sys.stdin.buffer)
    out = FileStream(sys.stderr.buffer)

    kern = reactor.get_kernel()

    print("Type stuff, end with Q")
    kern.run(user2err(inp, out))


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
