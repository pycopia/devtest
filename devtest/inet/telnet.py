"""TELNET client module.

Forked from Python's telnetlib and modified.  Originally forked into pycopia
project, adding better support for asynchronous frameworks. Now re-forked here.
Original module had no licensing so assuming PSF.
"""

import os
import struct
import socket

from devtest import logging


__all__ = ["Telnet", "get_telnet"]

# Telnet protocol defaults
TELNET_PORT = 23


def byte(val):
    return struct.pack("B", val)


# Telnet protocol characters (don't change)
IAC   = byte(255)  # "Interpret As Command"
DONT  = byte(254)  # 0xfe
DO    = byte(253)  # 0xfd
WONT  = byte(252)  # 0xfc
WILL  = byte(251)  # 0xfb
SB    = byte(250)  # sub negotiation 0xfa
GA    = byte(249)  # Go ahead
EL    = byte(248)  # Erase Line
EC    = byte(247)  # Erase character
AYT   = byte(246)  # Are You There
AO    = byte(245)  # Abort output
IP    = byte(244)  # Interrupt Process
BREAK = byte(243)  # NVT character BRK.
DM    = byte(242)  # Data Mark.

# The data stream portion of a Synch.
# This should always be accompanied by a TCP Urgent notification.
NOP   = byte(241)  # No operation.
SE    = byte(240)  # End of subnegotiation parameters.

IAC2 = IAC + IAC  # double IAC for escaping

# NVT special codes
NULL = byte(0)
BELL = byte(7)
BS  = byte(8)
HT = byte(9)
LF = byte(10)
VT = byte(11)
FF = byte(12)
CR = byte(13)
CRLF = CR + LF
CRNULL = CR + NULL


# Telnet protocol options code (don't change)
# These ones all come from arpa/telnet.h
BINARY = byte(0)  # 8-bit data path
ECHO = byte(1)  # echo
RCP = byte(2)  # prepare to reconnect
SGA = byte(3)  # suppress go ahead
NAMS = byte(4)  # approximate message size
STATUS = byte(5)  # give status
TM = byte(6)  # timing mark
RCTE = byte(7)  # remote controlled transmission and echo
NAOL = byte(8)  # negotiate about output line width
NAOP = byte(9)  # negotiate about output page size
NAOCRD = byte(10)  # negotiate about CR disposition
NAOHTS = byte(11)  # negotiate about horizontal tabstops
NAOHTD = byte(12)  # negotiate about horizontal tab disposition
NAOFFD = byte(13)  # negotiate about formfeed disposition
NAOVTS = byte(14)  # negotiate about vertical tab stops
NAOVTD = byte(15)  # negotiate about vertical tab disposition
NAOLFD = byte(16)  # negotiate about output LF disposition
XASCII = byte(17)  # extended ascii character set
LOGOUT = byte(18)  # force logout
BM = byte(19)  # byte macro
DET = byte(20)  # data entry terminal
SUPDUP = byte(21)  # supdup protocol
SUPDUPOUTPUT = byte(22)  # supdup output
SNDLOC = byte(23)  # send location
TTYPE = byte(24)  # terminal type
EOR = byte(25)  # end or record
TUID = byte(26)  # TACACS user identification
OUTMRK = byte(27)  # output marking
TTYLOC = byte(28)  # terminal location number
VT3270REGIME = byte(29)  # 3270 regime
X3PAD = byte(30)  # X.3 PAD
NAWS = byte(31)  # window size
TSPEED = byte(32)  # terminal speed
LFLOW = byte(33)  # remote flow control
LINEMODE = byte(34)  # Linemode option
XDISPLOC = byte(35)  # X Display Location
OLD_ENVIRON = byte(36)  # Old - Environment variables
AUTHENTICATION = byte(37)  # Authenticate
ENCRYPT = byte(38)  # Encryption option
NEW_ENVIRON = byte(39)  # New - Environment variables

# the following ones come from
# http://www.iana.org/assignments/telnet-options
# Unfortunately, that document does not assign identifiers
# to all of them, so we are making them up
TN3270E = byte(40)  # TN3270E
XAUTH = byte(41)  # XAUTH
CHARSET = byte(42)  # CHARSET
RSP = byte(43)  # Telnet Remote Serial Port
COM_PORT_OPTION = byte(44)  # Com Port Control Option
SUPPRESS_LOCAL_ECHO = byte(45)  # Telnet Suppress Local Echo
TLS = byte(46)  # Telnet Start TLS
KERMIT = byte(47)  # KERMIT
SEND_URL = byte(48)  # SEND-URL
FORWARD_X = byte(49)  # FORWARD_X
PRAGMA_LOGON = byte(138)  # TELOPT PRAGMA LOGON
SSPI_LOGON = byte(139)  # TELOPT SSPI LOGON
PRAGMA_HEARTBEAT = byte(140)  # TELOPT PRAGMA HEARTBEAT
EXOPL = byte(255)  # Extended-Options-List
NOOPT = byte(0)


# COM control sub commands, RFC 2217
SET_BAUDRATE        =  byte(1)
SET_DATASIZE        =  byte(2)
SET_PARITY          =  byte(3)
SET_STOPSIZE        =  byte(4)
SET_CONTROL         =  byte(5)
NOTIFY_LINESTATE    =  byte(6)
NOTIFY_MODEMSTATE   =  byte(7)
FLOWCONTROL_SUSPEND =  byte(8)
FLOWCONTROL_RESUME  =  byte(9)
SET_LINESTATE_MASK  =  byte(10)
SET_MODEMSTATE_MASK =  byte(11)
PURGE_DATA          =  byte(12)

RESP_SET_BAUDRATE        =  byte(101)
RESP_SET_DATASIZE        =  byte(102)
RESP_SET_PARITY          =  byte(103)
RESP_SET_STOPSIZE        =  byte(104)
RESP_SET_CONTROL         =  byte(105)
RESP_NOTIFY_LINESTATE    =  byte(106)
RESP_NOTIFY_MODEMSTATE   =  byte(107)
RESP_FLOWCONTROL_SUSPEND =  byte(108)
RESP_FLOWCONTROL_RESUME  =  byte(109)
RESP_SET_LINESTATE_MASK  =  byte(110)
RESP_SET_MODEMSTATE_MASK =  byte(111)
RESP_PURGE_DATA          =  byte(112)


class TelnetError(Exception):
    pass


class BadConnectionError(TelnetError):
    pass


class Telnet:

    def __init__(self, host=None, port=TELNET_PORT, logfile=None, sock=None):
        """A telnet connection.
        """
        self._logfile = logfile
        self.reset()
        if host:
            self.open(host, port)
        elif sock:
            self.sock = sock
            self._init_connection()

    def __enter__(self):
        return self

    def __exit__(self, extype, exvalue, traceback):
        self.close()
        return False

    def __str__(self):
        return "Telnet({!r:s}, {:d}): {} ({})".format(
            self.host, self.port,
            "open" if not self.eof else "closed",
            "binary" if self._binary else "nonbinary",)

    def open(self, host, port=TELNET_PORT):
        """Open a conneciton to a host.
        """
        if not self.sock:
            self.host = str(host)
            self.port = int(port)
            self.sock = socket.create_connection((self.host, self.port))
            self._init_connection()

    def settimeout(self, timeout):
        if self.sock:
            self.sock.settimeout(timeout)

    def gettimeout(self):
        if self.sock:
            return self.sock.gettimeout()

    def _init_connection(self):
        self._sendall(
            IAC + DO + BINARY +
            IAC + DO + SGA +
            IAC + DONT + ECHO +
            IAC + WILL + COM_PORT_OPTION)
        self._fill_rawq(12)
        self._process_rawq()
        self._closed = 0
        self.eof = 0

    def set_logfile(self, lf):
        self._logfile = lf

    def fileno(self):
        """Return the fileno() of the socket object used internally."""
        return self.sock.fileno()

    def close(self):
        if self.sock:
            self.sock.close()
            self.reset()
        self.eof = 1

    def reset(self):
        self.sock = None
        self.eof = 0
        self._closed = 1
        self._rawq = b''
        self._q = b''
        self._qi = 0
        self._irawq = 0
        self.iacseq = b''  # Buffer for IAC sequence.
        self.sb = 0  # flag for SB and SE sequence.
        self.sbdataq = b''
        self._binary = False
        self._sga = False
        self._do_com = False
        self._linestate = None
        self._modemstate = None
        self._suspended = False

    linestate = property(lambda self: self._linestate)
    modemstate = property(lambda self: self._modemstate)
    closed = property(lambda self: self._closed)

    def write(self, text):
        """Write a string to the socket, doubling any IAC characters.

        Can block if the connection is blocked.  May raise
        socket.error if the connection is closed.
        """
        if IAC in text:
            text = text.replace(IAC, IAC2)
        if self._logfile:
            self._logfile.write("   ->: {!r}\n".format(text))
        self.sock.sendall(text)

    def read(self, amt):
        while not self._q:
            self._fill_rawq()
            self._process_rawq()
        d = self._q[self._qi:self._qi + amt]
        self._qi += amt
        if self._qi >= len(self._q):
            self._q = b''
            self._qi = 0
        return d

    def read_until(self, patt):
        buf = b""
        while 1:
            c = self.read(1)
            if c == b"":
                raise IOError("EOF during read_until({!r}).".format(patt))
            buf += c
            i = buf.find(patt)
            if i >= 0:
                return buf[:i]

    def _fill_rawq(self, n=256):
        if self._irawq >= len(self._rawq):
            self._rawq = b''
            self._irawq = 0
        buf = self.sock.recv(n)
        if self._logfile:
            self._logfile.write("<-{0:003d}: {1!r:s}\n".format(len(buf), buf))
        self.eof = (not buf)
        self._rawq += buf

    def _rawq_getchar(self):
        if not self._rawq:
            self._fill_rawq()
            if self.eof:
                raise EOFError("No data received")
        c = byte(self._rawq[self._irawq])
        self._irawq += 1
        if self._irawq >= len(self._rawq):
            self._rawq = b''
            self._irawq = 0
        return c

    def _process_rawq(self):
        buf = [b'', b'']  # data buffer and SB buffer
        try:
            while self._rawq:
                c = self._rawq_getchar()
                if not self.iacseq:
                    if c == NULL:
                        continue
                    if c == b"\021":
                        continue
                    if c != IAC:
                        buf[self.sb] += c
                        continue
                    else:
                        self.iacseq += c
                elif len(self.iacseq) == 1:
                    if c in (DO, DONT, WILL, WONT):
                        self.iacseq += c
                        continue

                    self.iacseq = b''
                    if c == IAC:
                        buf[self.sb] += c
                    else:
                        if c == SB:  # SB ... SE start.
                            self.sb = 1
                            self.sbdataq = b''
                        elif c == SE:
                            self.sb = 0
                            self.sbdataq += buf[1]
                            buf[1] = b''
                            self._suboption()
                        else:
                            logging.warning('Telnet: IAC {!r} not recognized'.format(c))
                elif len(self.iacseq) == 2:
                    cmd = byte(self.iacseq[1])
                    self.iacseq = b''
                    if cmd in (DO, DONT, WILL, WONT):
                        self._neg_option(cmd, c)
                    else:
                        logging.error("telnet bad command: {!r}".format(cmd))
        except EOFError:
            self.iacseq = b''  # Reset on EOF
            self.sb = 0
        self._q += buf[0]
        self.sbdataq += buf[1]

    def _sendall(self, data, opt=0):
        if self._logfile:
            self._logfile.write("cmd->: {!r}\n".format(data))
        self.sock.sendall(data, opt)

    def _neg_option(self, cmd, opt):
        if cmd == DO:  # 0xfd
            if opt == BINARY:
                self._sendall(IAC + WILL + BINARY)
            elif opt == SGA:
                self._sendall(IAC + WILL + SGA)
            elif opt == COM_PORT_OPTION:
                self._do_com = True
                # Don't bother us with modem state changes
                self._sendall(
                    IAC + SB + COM_PORT_OPTION + SET_MODEMSTATE_MASK +
                    b"\x00" + IAC + SE)
            else:
                self._sendall(IAC + WONT + opt)
        elif cmd == WILL:
            if opt == BINARY:
                self._binary = True
            elif opt == SGA:
                self._sga = True
            elif opt == COM_PORT_OPTION:
                self._do_com = True
            else:
                self._sendall(IAC + DONT + opt)
        elif cmd == DONT:
            if opt in (BINARY, SGA):
                raise BadConnectionError("Server doesn't want binary connection.")
            else:
                self._sendall(IAC + WONT + opt)
        elif cmd == WONT:
            if opt in (BINARY, SGA):
                raise BadConnectionError("Could not negotiate binary path.")

    def _suboption(self):
        subopt = self.sbdataq
        self.sbdataq = b''
        if len(subopt) != 3:
            logging.error("Bad suboption recieved: {!r}".format(subopt))
            return
        if subopt[0] == COM_PORT_OPTION:
            comopt = subopt[1]
            if comopt == RESP_NOTIFY_LINESTATE:
                self._linestate = LineState(subopt[2])
            elif comopt == RESP_NOTIFY_MODEMSTATE:
                self._modemstate = ModemState(subopt[2])
            elif comopt == RESP_FLOWCONTROL_SUSPEND:
                self._suspended = True
                logging.warning("Telnet: requested to suspend tx.")
            elif comopt == RESP_FLOWCONTROL_RESUME:
                self._suspended = False
                logging.warning("Telnet: requested to resume tx.")
            else:
                logging.warning(
                    "Telnet: unhandled COM opton: {}".format(repr(subopt)))
        else:
            logging.warning(
                "Telnet: unhandled subnegotion: {}".format(repr(subopt)))

    def interrupt(self):
        self._sendall(IAC + IP)
        self._fill_rawq(1)
        self._process_rawq()

    def abort_output(self):
        self._sendall(IAC + AO)
        self._fill_rawq(1)
        self._process_rawq()

    def sync(self):
        self._sendall(IAC + DM, socket.MSG_OOB)
        self._process_rawq()

    def send_command(self, cmd):
        self._sendall(IAC + cmd)

    def send_option(self, disp, opt):
        self._sendall(IAC + disp + opt)

    def set_baud(self, rate):
        self.send_com_option(SET_BAUDRATE, struct.pack("!I", rate))

    def send_com_option(self, opt, value):
        if self._do_com:
            self._sendall(IAC + SB + COM_PORT_OPTION + opt + value + IAC + SE)
        else:
            raise TelnetError("Use of COM option when not negotiated.")

    def upload(self, filename):
        """Basic upload using cat.
        """
        text = open(filename, 'rb').read()
        sockfd = self.sock.fileno()
        os.write(sockfd, b"cat - > %b\r" % (
            os.path.basename(filename).encode("ascii"),))
        os.write(sockfd, text)
        os.write(sockfd, b"\r" + chr(4))

    def read_handler(self):
        self._fill_rawq()
        self._process_rawq()


class LineState:

    def __init__(self, code):
        self.timeouterror = code & 128
        self.transmit_shift_register_empty = code & 64
        self.transmit_holding_register_empty = code & 32
        self.break_detect_error = code & 16
        self.framing_error = code & 8
        self.parity_error = code & 4
        self.overrun_error = code & 2
        self.data_ready = code & 1


class ModemState(object):
    def __init__(self, code):
        self.carrier_detect = bool(code & 128)
        self.ring_indicator = bool(code & 64)
        self.dataset_ready = bool(code & 32)
        self.clear_to_send = bool(code & 16)
        self.delta_rx_detect = bool(code & 8)
        self.ring_indicator = bool(code & 4)
        self.delta_dataset_ready = bool(code & 2)
        self.delta_clear_to_send = bool(code & 1)

    def __str__(self):
        return """ModemState:
         carrier_detect: {}
         ring_indicator: {}
          dataset_ready: {}
          clear_to_send: {}
        delta_rx_detect: {}
         ring_indicator: {}
    delta_dataset_ready: {}
    delta_clear_to_send: {}
        """.format(
            self.carrier_detect,
            self.ring_indicator,
            self.dataset_ready,
            self.clear_to_send,
            self.delta_rx_detect,
            self.ring_indicator,
            self.delta_dataset_ready,
            self.delta_clear_to_send)


def get_telnet(host, port=TELNET_PORT, logfile=None):
    return Telnet(host, port, logfile)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
