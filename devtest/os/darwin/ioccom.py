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
Compute ioctl commands.

from <sys/ioccom.h>
"""

import struct

sizeof = struct.calcsize

INT = sizeof("i")
INT2 = sizeof("ii")
UINT = sizeof("I")
LONG = sizeof("l")
ULONG = sizeof("L")
SHORT = sizeof("h")
USHORT = sizeof("H")
CHAR = sizeof("c")

# Ioctl's have the command encoded in the lower word, and the size of
# any in or out parameters in the upper word.  The high 3 bits of the
# upper word are used to encode the in/out status of the parameter.

IOCPARM_MASK = 0x1fff  # parameter length, at most 13 bits


def IOCPARM_LEN(x):
    return ((x >> 16) & IOCPARM_MASK)


def IOCBASECMD(x):
    return x & ~(IOCPARM_MASK << 16)


def IOCGROUP(x):
    return (x >> 8) & 0xff


IOCPARM_MAX = IOCPARM_MASK + 1  # max size of ioctl args

# no parameters
IOC_VOID = 0x20000000

# copy parameters out
IOC_OUT = 0x40000000

# copy parameters in
IOC_IN = 0x80000000

# copy paramters in and out
IOC_INOUT = IOC_IN | IOC_OUT

# mask for IN/OUT/VOID
IOC_DIRMASK = 0xe0000000


def _IOC(inout, group, num, length):
    return inout | ((length & IOCPARM_MASK) << 16) | (ord(group) << 8) | (num)


def _IO(g, n):
    return _IOC(IOC_VOID, g, n, 0)


def _IOR(g, n, t):
    return _IOC(IOC_OUT, g, n, t)


def _IOW(g, n, t):
    return _IOC(IOC_IN, g, n, t)


def _IOWR(g, n, t):
    return _IOC(IOC_INOUT, g, n, t)


_IORW = _IOWR


def _test(argv):
    import termios
    assert termios.TIOCOUTQ == 1074033779
    TIOCOUTQ = _IOR('t', 115, INT)  # output queue size
    assert termios.TIOCOUTQ == TIOCOUTQ
    assert _IOW('T', 2, ULONG) == 2148029442


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
