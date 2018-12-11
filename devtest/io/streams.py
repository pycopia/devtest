"""IO for streams.

Use the Stream object from here. Collects the curio supplies Stream objects and
adds some new ones.
"""

from __future__ import generator_stop

from curio.io import _Fd, StreamBase, FileStream, SocketStream, Socket  # noqa
from curio.channel import Connection, Channel


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
