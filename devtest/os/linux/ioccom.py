# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Linux ioctl macros. Adapted from /usr/include/asm/ioctl.h
"""

# ioctl command encoding: 32 bits total, command in lower 16 bits,
# size of the parameter structure in the lower 14 bits of the
# upper 16 bits.
# Encoding the size of the parameter structure in the ioctl request
# is useful for catching programs compiled with old versions
# and to avoid overwriting user space outside the user buffer area.
# The highest 2 bits are reserved for indicating the ``access mode''.
# NOTE: This limits the max parameter size to 16kB -1 !
#
#
# The following is for compatibility across the various Linux
# platforms.  The i386 ioctl numbering scheme doesn't really enforce
# a type field.  De facto, however, the top 8 bits of the lower 16
# bits are indeed used as a type field, so we might just as well make
# this explicit here.  Please be sure to use the decoding macros
# below from now on.

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

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2
_IOC_NRMASK = ((1 << _IOC_NRBITS) - 1)
_IOC_TYPEMASK = ((1 << _IOC_TYPEBITS) - 1)
_IOC_SIZEMASK = ((1 << _IOC_SIZEBITS) - 1)
_IOC_DIRMASK = ((1 << _IOC_DIRBITS) - 1)
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = (_IOC_NRSHIFT + _IOC_NRBITS)
_IOC_SIZESHIFT = (_IOC_TYPESHIFT + _IOC_TYPEBITS)
_IOC_DIRSHIFT = (_IOC_SIZESHIFT + _IOC_SIZEBITS)

IOCSIZE_MASK = (_IOC_SIZEMASK << _IOC_SIZESHIFT)
IOCSIZE_SHIFT = (_IOC_SIZESHIFT)

###
# direction bits
_IOC_NONE = 0
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(dir, type, nr, FMT):
        return int((((dir)  << _IOC_DIRSHIFT) |
                   ((type) << _IOC_TYPESHIFT) |
                   ((nr)   << _IOC_NRSHIFT) |
                   ((FMT) << _IOC_SIZESHIFT)) & 0xffffffff)


# used to create numbers
# type is the assigned type from the kernel developers
# nr is the base ioctl number (defined by driver writer)
# FMT is a struct module format string.
def _IO(type, nr):
    return _IOC(_IOC_NONE, (type), (nr), 0)


def _IOR(type, nr, FMT):
    return _IOC(_IOC_READ, (type), (nr), sizeof(FMT))


def _IOW(type, nr, FMT):
    return _IOC(_IOC_WRITE, (type), (nr), sizeof(FMT))


def _IOWR(type, nr, FMT):
    return _IOC(_IOC_READ | _IOC_WRITE, type, nr, sizeof(FMT))


# used to decode ioctl numbers
def _IOC_DIR(nr):
    return (((nr) >> _IOC_DIRSHIFT) & _IOC_DIRMASK)


def _IOC_TYPE(nr):
    return (((nr) >> _IOC_TYPESHIFT) & _IOC_TYPEMASK)


def _IOC_NR(nr):
    return (((nr) >> _IOC_NRSHIFT) & _IOC_NRMASK)


def _IOC_SIZE(nr):
    return (((nr) >> _IOC_SIZESHIFT) & _IOC_SIZEMASK)
