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
Utility functions for sockets network functions.
"""

import struct
import fcntl
from errno import EADDRNOTAVAIL
from socket import (socket, getaddrinfo, gethostbyname, getfqdn, create_connection, error, gaierror,
                    IPPROTO_TCP, IPPORT_USERRESERVED, AF_INET, SOCK_STREAM)

# Extra ioctl numbers
SIOCINQ = 0x541B
SIOCOUTQ = 0x5411


def check_port(host, port):
    """Checks a TCP port on a remote host for a listener. Returns true if a
    connection is possible, false otherwise."""
    try:
        s = create_connection((host, port))
    except error:
        return False
    s.close()
    return True


def verify_host(host, port=None):
    """Verify a host name is real (in the DNS) and the port is reachable, if
    given.
    """
    try:
        gailist = getaddrinfo(host, port, proto=IPPROTO_TCP)
    except gaierror:
        return False
    if gailist:
        if port:
            return check_port(host, port)
        else:
            return True
    return False


def islocal(host):
    """islocal(host) tests if the given host is ourself, or not."""
    # try to bind to the address, if successful it is local...
    ip = gethostbyname(getfqdn(host))
    s = socket(AF_INET, SOCK_STREAM)
    try:
        s.bind((ip, IPPORT_USERRESERVED + 1))
    except OSError as err:
        if err.errno == EADDRNOTAVAIL:
            return False
        else:
            raise
    else:
        s.close()
        return True


def inq(sock):
    """How many bytes are still in the kernel's input buffer?"""
    return struct.unpack("I", fcntl.ioctl(sock.fileno(), SIOCINQ, b'\0\0\0\0'))[0]


def outq(sock):
    """How many bytes are still in the kernel's output buffer?"""
    return struct.unpack("I", fcntl.ioctl(sock.fileno(), SIOCOUTQ, b'\0\0\0\0'))[0]


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
