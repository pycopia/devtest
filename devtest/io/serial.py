"""
Simple interface to serial ports using termios.
This serial port interface support non-blocking, asychronous designs. You can
use it with the asyncio module.
"""
# flake8: noqa: F403,F405

import sys
import os
import stat
from fcntl import ioctl, fcntl, F_SETFL, F_GETFL
from array import array
from struct import pack, unpack
from functools import wraps
# You may use this module instead of the stock termios module.
from termios import *
from io import RawIOBase


from devtest.os.ioccom import _IO, _IOW, ULONG, INT

# Indexes for termios list.
IFLAG = 0
OFLAG = 1
CFLAG = 2
LFLAG = 3
ISPEED = 4
OSPEED = 5
CC = 6

IFLAGS = ["IGNBRK", "BRKINT", "IGNPAR", "PARMRK", "INPCK", "ISTRIP",
          "INLCR", "IGNCR", "ICRNL", "IXON", "IXANY", "IXOFF", "IMAXBEL"]

OFLAGS = ["OPOST", "ONLCR", "OCRNL", "ONOCR", "ONLRET"]

CFLAGS = ["CSTOPB", "CREAD", "PARENB", "CLOCAL", "CRTSCTS"]

LFLAGS = ["ISIG", "ICANON", "ECHO", "ECHOE", "ECHOK", "ECHONL",
          "ECHOCTL", "ECHOPRT", "ECHOKE", "FLUSHO", "NOFLSH", "TOSTOP",
          "PENDIN", "IEXTEN"]

BAUDS = ["B0", "B50", "B75", "B110", "B134", "B150", "B200", "B300",
         "B600", "B1200", "B1800", "B2400", "B4800", "B9600", "B19200",
         "B38400", "B57600", "B115200", "B230400"]

CCHARS = ["VINTR", "VQUIT", "VERASE", "VKILL", "VEOF", "VSTART", "VSTOP",
          "VSUSP", "VEOL", "VREPRINT", "VDISCARD", "VWERASE", "VLNEXT",
          "VEOL2"]


# Extra ioctls for Darwin
if sys.platform == "darwin":

    TIOCDRAIN = _IO('t', 94)  # wait till output drained

# Sets the receive latency (in microseconds) with the default
# value of 0 meaning a 256 / 3 character delay latency.
    IOSSDATALAT = _IOW('T', 0, ULONG)

# Controls the pre-emptible status of IOSS based serial dial in devices
# (i.e. /dev/tty.* devices).  If true an open tty.* device is pre-emptible by
# a dial out call.  Once a dial in call is established then setting pre-empt
# to false will halt any further call outs on the cu device.
    IOSSPREEMPT = _IOW('T', 1, INT)

# Sets the input speed and output speed to a non-traditional baud rate
    IOSSIOSPEED = _IOW('T', 2, ULONG)
else:
    IOSSIOSPEED = 0


def set_baud(fd, baud):
    """Set the baud rate on the given file descriptor."""
    mod = sys.modules[__name__]
    try:
        sym = getattr(mod, "B%s" % baud)
        iflags, oflags, cflags, lflags, ispeed, ospeed, cc = tcgetattr(fd)
        ispeed = ospeed = sym
        tcsetattr(fd, TCSANOW,
                  [iflags, oflags, cflags, lflags, ispeed, ospeed, cc])
    except AttributeError:
        if IOSSIOSPEED != 0:
            ioctl(fd, IOSSIOSPEED, pack("L", int(baud)))
        else:
            raise OSError("Invalid baud")


def flag_string(fd):
    """Get the termios flags from the file descriptor and return a human friend
    string representation.
    """
    mod = sys.modules[__name__]
    [iflags, oflags, cflags, lflags, ispeed, ospeed, cc] = tcgetattr(fd)
    chars = []
    ires = []
    ores = []
    cres = []
    lres = []
    for cname in CCHARS:
        cval = cc[getattr(mod, cname)][0]
        cval = (("^" + chr(cval + 64)) if cval < 32 else
                ("<undef>" if cval > 127 else ("^" + chr(cval-64))))
        chars.append("{}={}".format(cname[1:].lower(), cval))
    chars.append("time={}; min={}".format(cc[VTIME], cc[VMIN]))
    for flag in IFLAGS:
        if iflags & getattr(mod, flag):
            ires.append(flag.lower())
        else:
            ires.append("-%s" % (flag.lower(),))
    for flag in OFLAGS:
        if oflags & getattr(mod, flag):
            ores.append(flag.lower())
        else:
            ores.append("-%s" % (flag.lower(),))
    for flag in CFLAGS:
        if cflags & getattr(mod, flag):
            cres.append(flag.lower())
        else:
            cres.append("-%s" % (flag.lower(),))
    for flag in LFLAGS:
        if lflags & getattr(mod, flag):
            lres.append(flag.lower())
        else:
            lres.append("-%s" % (flag.lower(),))
    s = ["speed {} baud out; {} in;".format(ospeed, ispeed)]
    s.append("lflags: {}".format(" ".join(lres)))
    s.append("iflags: {}".format(" ".join(ires)))
    s.append("oflags: {}".format(" ".join(ores)))
    s.append("cflags: {}".format(" ".join(cres)))
    s.append("cchars: {}".format("; ".join(chars)))
    return "\n".join(s)


def setraw(fd, when=TCSAFLUSH):
    """Put tty into a raw mode."""
    mode = tcgetattr(fd)
    old = mode[:]
    mode[IFLAG] &= ~(BRKINT | ICRNL | INLCR | INPCK | ISTRIP | IXON | IXOFF)
    mode[IFLAG] |= (IGNPAR | IGNBRK)
    mode[OFLAG] &= ~(OPOST)
    mode[OFLAG] |= (ONLCR)
    mode[CFLAG] &= ~(PARENB)
    mode[CFLAG] |= (CS8 | CLOCAL | CREAD | HUPCL)
    mode[LFLAG] &= ~(ECHO | ICANON | IEXTEN | ISIG)
    mode[LFLAG] |= (ECHOCTL)
    mode[CC][VMIN] = 1
    mode[CC][VTIME] = 0
    tcsetattr(fd, when, mode)
    return old


def set_min_time(fd, vmin, vtime, when=TCSANOW):
    mode = tcgetattr(fd)
    old = mode[:]
    mode[CC][VMIN] = int(vmin)
    mode[CC][VTIME] = int(vtime)
    tcsetattr(fd, when | TCSASOFT, mode)
    return old


def set_8N1(fd, when=TCSAFLUSH):
    """Set 8 bits, no parity, one stop bit on the tty with the given file
    descriptor.
    """
    mode = tcgetattr(fd)
    old = mode[:]
    mode[IFLAG] &= ~(INPCK | ISTRIP)
    mode[IFLAG] |= (IGNPAR)
    mode[CFLAG] &= ~(PARENB | CSTOPB)
    mode[CFLAG] |= CS8
    tcsetattr(fd, when, mode)
    return old


def set_7E1(fd, when=TCSAFLUSH):
    """Set 7 bits, even parity, one stop bit on the tty with the given file
    descriptor.
    """
    mode = tcgetattr(fd)
    old = mode[:]
    mode[IFLAG] &= ~(IGNPAR | ISTRIP)
    mode[IFLAG] |= (INPCK)
    mode[CFLAG] &= ~(CSTOPB | PARODD)
    mode[CFLAG] |= (CS7 | PARENB)
    tcsetattr(fd, when, mode)
    return old


def set_mode(fd: int, parity: str, data_bits: int, stop_bits: int):
    """Set the parity, data bits, and stop bits on a file descriptor."""
    mode = tcgetattr(fd)
    P = parity.upper()[0]
    if P == "N":
        mode[CFLAG] &= ~(PARENB | PARODD)
    elif P == "E":
        mode[CFLAG] |= PARENB
    elif P == "O":
        mode[CFLAG] |= (PARENB | PARODD)
    else:
        raise ValueError("Parity must be None, Even, or Odd")
    if data_bits == 7:
        mode[CFLAG] |= CS7
    elif data_bits == 8:
        mode[CFLAG] |= CS8
    else:
        raise ValueError("Bits must be 7 or 8")
    if stop_bits == 2:
        mode[CFLAG] |= CSTOPB
    else:
        mode[CFLAG] &= ~CSTOPB
    tcsetattr(fd, TCSAFLUSH, mode)


_MODEMAP = {
    "rb": os.O_NOCTTY,
    "wb": os.O_WRONLY | os.O_NOCTTY,
    "w+b":  os.O_RDWR | os.O_NOCTTY,
    "r+b":  os.O_RDWR | os.O_NOCTTY,
}


def rawstdin(meth):
    """Decorator for temporarily using stdin in raw mode."""
    @wraps(meth)
    def wrapcleantty(*args, **kwargs):
        savestate = tcgetattr(sys.stdin)
        setraw(sys.stdin.fileno())
        try:
            rv = meth(*args, **kwargs)
        finally:
            tcsetattr(sys.stdin, TCSAFLUSH, savestate)
        return rv
    return wrapcleantty


class SerialPort(RawIOBase):
    """Simple and fast interface to a serial/tty.
    Sets the "exclusive" flag on the tty port so that only one process may open
    it at a time.

    Provide the device path to open the "cu" device.

    Implements a basic file-like IO to the serial port (read, write, fileno,
    close, and closed attribute).
    """
    def __init__(self, fname=None, mode="w+b", setup="115200 8N1", config=None):
        # In case of exception here, so the close method will still work.
        self._fd = None
        self.name = "unknown"
        if fname:
            self.open(fname, mode, setup, config)

    def __repr__(self):
        return "{}(fname={!r})".format(self.__class__.__name__, self.name)

    def __str__(self):
        if self._fd is not None:
            fl = flag_string(self._fd)
            return "{}:\n{}".format(self.name, fl)
        else:
            return "SerialPort {!r} is closed.".format(self.name)

    def fileno(self):
        if self._fd is None:
            raise IOError("fileno() on closed file.")
        return self._fd

    @property
    def closed(self):
        return self._fd is None

    def open(self, fname, mode="w+b", setup="115200 8N1", config=None):
        self.close()
        st = os.stat(fname).st_mode
        if not stat.S_ISCHR(stat.S_IFMT(st)):
            raise ValueError("{0} is not a character device.".format(fname))
        if "b" not in mode:
            raise ValueError("Only binary modes supported for mode.")
        self._fd = fd = os.open(fname, _MODEMAP[mode])
        self._savestate = tcgetattr(fd)
        # open exclusively, close on exec
        ioctl(fd, TIOCEXCL)
        ioctl(fd, FIOCLEX)
        # set raw mode
        setraw(fd)
        # set no flow control
        modembits = array("I", [0])
        ioctl(fd, TIOCMGET, modembits, True)
        modembits[0] &= ~(TIOCM_DTR | TIOCM_RTS)
        ioctl(fd, TIOCMSET, modembits)
        tcflush(fd, TCIOFLUSH)
        if config:
            self.config(config)
        else:
            self.set_serial(setup)
        self.name = fname

    def close(self):
        if self._fd is not None:
            fd = self._fd
            self._fd = None
            self.name = "unknown"
            tcsetattr(fd, TCSAFLUSH, self._savestate)
            ioctl(fd, TIOCNXCL)
            return os.close(fd)

    def seekable(self):
        return False

    def set_baud(self, baud):
        set_baud(self._fd, baud)

    def set_min_time(self, vmin, vtime, when=TCSANOW):
        set_min_time(self._fd, vmin, vtime, when=when)

    def set_serial(self, spec):
        """Quick and easy way to setup the serial port.
        Supply a string such as "9600 8N1".
        """
        fd = self._fd
        baud, mode = spec.split()
        if mode == "8N1":
            set_8N1(fd)
        elif mode == "7E1":
            set_7E1(fd)
        else:
            raise ValueError("set_serial: bad serial string.")
        set_baud(fd, baud)

    def config(self, conf):
        """Alternate way to set up serial parameters.

        supply a string like: baud,parity,data bits,stop_bits

        Example:
            '9600,N,8,1'
        """
        fd = self._fd
        baud, parity, data_bits, stop_bits = 115200, "N", 8, 1
        baud, *rest = conf.split(",")
        if rest:
            parity, data_bits, stop_bits = rest
        set_mode(fd, parity.strip(), int(data_bits), int(stop_bits))
        set_baud(fd, int(baud))

    def send_break(self):
        tcsendbreak(self._fd, 0)

    def discard(self):
        """Discard IO queue."""
        tcflush(self._fd, TCIOFLUSH)

    def get_outqueue(self):
        "Return number of bytes in output queue."""
        v = ioctl(self._fd, TIOCOUTQ, b'\x00\x00\x00\x00')
        return unpack("i", v)[0]

    def readinto(self, buf):
        data = os.read(self._fd, len(buf))
        ld = len(data)
        if ld:
            buf[:ld] = data
        return ld

    def write(self, data):
        return os.write(self._fd, data)

    def set_nonblocking(self):
        set_nonblocking(self._fd)

    def set_blocking(self):
        set_blocking(self._fd)


def set_nonblocking(fd):
    flags = fcntl(fd, F_GETFL)
    flags |= os.O_NONBLOCK
    fcntl(fd, F_SETFL, flags)


def set_blocking(fd):
    flags = fcntl(fd, F_GETFL)
    flags &= ~os.O_NONBLOCK
    fcntl(fd, F_SETFL, flags)


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
