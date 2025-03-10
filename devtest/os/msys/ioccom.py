"""MSYS ioctl macros. Adapted from /usr/include/sys/ioctl.h
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

###
# direction bits
_IOC_NONE = 0
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(dir, type, nr, size):
    return int((((dir) << _IOC_DIRSHIFT) | ((type) << _IOC_TYPESHIFT) | ((nr) << _IOC_NRSHIFT) |
                ((size) << _IOC_SIZESHIFT)) & 0xffffffff)


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
