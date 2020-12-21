# python wrapper for signalfd. The signalfd call is Linux specific.
# cython: language_level=3
#
#    Copyright (C) 2020-  Keith Dart <keith@kdart.com>
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.

from cpython.bool cimport bool
from posix.types cimport pid_t, sigset_t, uid_t
from posix.unistd cimport close, read
from libc.stdint cimport uint8_t, uint16_t, uint32_t, int32_t, uint64_t
from libc.signal cimport SIGCHLD
from posix.signal cimport sigaddset, sigemptyset, SIG_BLOCK


cdef extern from "<signal.h>" nogil:
    int pthread_sigmask(int, const sigset_t *, sigset_t *)


cdef extern from "string.h":
    char *strerror(int errnum)


cdef extern from "errno.h":
    int errno
    enum: EINTR
    enum: EAGAIN


cdef extern from "sys/signalfd.h" nogil:
    int signalfd(int, const sigset_t *, int)

    enum: SFD_CLOEXEC
    enum: SFD_NONBLOCK

    cdef struct signalfd_siginfo:
        uint32_t ssi_signo
        int32_t ssi_errno
        int32_t ssi_code
        uint32_t ssi_pid
        uint32_t ssi_uid
        int32_t ssi_fd
        uint32_t ssi_tid
        uint32_t ssi_band
        uint32_t ssi_overrun
        uint32_t ssi_trapno
        int32_t ssi_status
        int32_t ssi_int
        uint64_t ssi_ptr
        uint64_t ssi_utime
        uint64_t ssi_stime
        uint64_t ssi_addr
        uint16_t ssi_addr_lsb
        uint16_t __pad2
        int32_t ssi_syscall
        uint64_t ssi_call_addr
        uint32_t ssi_arch
        uint8_t __pad[28]


class SignalInfo:
    __slots__ = ("ssi_signo", "ssi_errno", "ssi_code", "ssi_pid", "ssi_uid", "ssi_fd", "ssi_tid",
                 "ssi_band", "ssi_overrun", "ssi_trapno", "ssi_status", "ssi_int", "ssi_ptr",
                 "ssi_utime", "ssi_stime", "ssi_addr", "ssi_addr_lsb", "ssi_syscall",
                 "ssi_call_addr", "ssi_arch")

    @property
    def signo(self):
        return self.ssi_signo

    def __str__(self):
        if self.ssi_signo == SIGCHLD:
            return (f"SignalInfo: SIGCHLD: "
                    f"pid: {self.ssi_pid}, uid: {self.ssi_uid}, status: {self.ssi_status}")
        else:
            return f"SignalInfo: signal: {self.ssi_signo}"

cdef _SignalInfo_new(signalfd_siginfo *fdsi):
    si = SignalInfo()

    si.ssi_signo = fdsi.ssi_signo
    si.ssi_errno = fdsi.ssi_errno
    si.ssi_code = fdsi.ssi_code
    si.ssi_pid = fdsi.ssi_pid  # for SIGCHLD or SIGINT
    si.ssi_uid = fdsi.ssi_uid  # for SIGCHLD
    si.ssi_fd = fdsi.ssi_fd  # for SIGIO
    si.ssi_tid = fdsi.ssi_tid  # Timer ID for SIGALRM
    si.ssi_band = fdsi.ssi_band  # for SIGIO
    si.ssi_overrun = fdsi.ssi_overrun  # for timers
    si.ssi_trapno = fdsi.ssi_trapno
    si.ssi_status = fdsi.ssi_status  # for SIGCHLD
    si.ssi_int = fdsi.ssi_int
    si.ssi_ptr = fdsi.ssi_ptr
    si.ssi_utime = fdsi.ssi_utime  # for SIGCHLD
    si.ssi_stime = fdsi.ssi_stime  # for SIGCHLD
    si.ssi_addr = fdsi.ssi_addr
    si.ssi_addr_lsb = fdsi.ssi_addr_lsb
    si.ssi_syscall = fdsi.ssi_syscall
    si.ssi_call_addr = fdsi.ssi_call_addr
    si.ssi_arch = fdsi.ssi_arch
    return si


cdef class FDSignals:
    """FDSignals(signals, nonblocking=False, close_on_exec=False)

    Accept signals using a file.

    See signalfd(2) for more information.

    Args:
        signals: iterable if signal.SIG* values.
        nonblocking: if True, set file descriptor to NON_BLOCKING mode.
        close_on_exec: if True, set to close on exec.

    If nonblocking flag is true, the fd is made non-blocking.
    """

    cdef int _fd
    cdef sigset_t _sigset

    def __init__(self, signals, bool nonblocking=False, bool close_on_exec=False):
        cdef int fd = -1
        cdef int rv = 0
        cdef sigset_t sigset
        cdef int flags = 0

        if nonblocking:
            flags |= SFD_NONBLOCK
        if close_on_exec:
            flags |= SFD_CLOEXEC
        if sigemptyset(&sigset) == -1:
            raise OSError((errno, strerror(errno)))
        for sig in signals:
            if sigaddset(&sigset, <int>sig) == -1:
                raise OSError((errno, strerror(errno)))
        # When using signalfd the selected signals should be blocked for normal use.
        rv = pthread_sigmask(SIG_BLOCK, &sigset, NULL)
        if rv != 0:
            raise OSError((rv, strerror(rv)))
        fd = signalfd(-1, &sigset, flags)
        if fd == -1:
            raise OSError((errno, strerror(errno)))
        self._fd = fd

    def __dealloc__(self):
        self.close()

    def __nonzero__(self):
        if self._fd == -1:
            return False
        return True

    def close(self):
        if self._fd != -1:
            close(self._fd)
            self._fd = -1

    def fileno(self):
        return self._fd

    @property
    def closed(self):
        return self._fd == -1

    def read(self, int amt=-1):
        """Read siginfo from latest signal.

        The amt is ignored. It is for compatibility with file-like interface.

        Returns:
            A SignalInfo object.
        """
        cdef signalfd_siginfo fdsi
        rv = read(self._fd, &fdsi, sizeof(signalfd_siginfo))
        if rv == sizeof(signalfd_siginfo):
            return _SignalInfo_new(&fdsi)
        elif rv == -1 and errno == EAGAIN:
            raise BlockingIOError(strerror(errno))
        elif rv > 0:
            raise RuntimeError("FDSignals: bad read of siginfo")
        else:
            raise OSError((errno, strerror(errno)))
