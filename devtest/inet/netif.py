"""Network interface information.
"""

import sys
import enum
import socket
import ipaddress
from typing import List, Union
from fcntl import ioctl


class AddressFamily(enum.IntEnum):
    ARPHRD_NETROM = 0  # From KA9Q: NET/ROM pseudo.
    ARPHRD_ETHER = 1  # Ethernet 10/100Mbps.
    ARPHRD_EETHER = 2  # Experimental Ethernet.
    ARPHRD_AX25 = 3  # AX.25 Level 2.
    ARPHRD_PRONET = 4  # PROnet token ring.
    ARPHRD_CHAOS = 5  # Chaosnet.
    ARPHRD_IEEE802 = 6  # IEEE 802.2 Ethernet/TR/TB.
    ARPHRD_ARCNET = 7  # ARCnet.
    ARPHRD_APPLETLK = 8  # APPLEtalk.
    ARPHRD_DLCI = 15  # Frame Relay DLCI.
    ARPHRD_ATM = 19  # ATM.
    ARPHRD_METRICOM = 23  # Metricom STRIP (new IANA id).
    ARPHRD_IEEE1394 = 24  # IEEE 1394 IPv4 - RFC 2734.
    ARPHRD_EUI64 = 27  # EUI-64.
    ARPHRD_INFINIBAND = 32  # InfiniBand.
    # Dummy types for non ARP hardware
    ARPHRD_SLIP = 256
    ARPHRD_CSLIP = 257
    ARPHRD_SLIP6 = 258
    ARPHRD_CSLIP6 = 259
    ARPHRD_RSRVD = 260  # Notional KISS type.
    ARPHRD_ADAPT = 264
    ARPHRD_ROSE = 270
    ARPHRD_X25 = 271  # CCITT X.25.
    ARPHRD_HWX25 = 272  # Boards with X.25 in firmware.
    ARPHRD_CAN = 280  # Controller Area Network
    ARPHRD_PPP = 512
    ARPHRD_CISCO = 513  # Cisco HDLC.
    ARPHRD_LAPB = 516  # LAPB.
    ARPHRD_DDCMP = 517  # Digital's DDCMP.
    ARPHRD_RAWHDLC = 518  # Raw HDLC.
    ARPHRD_RAWIP = 519  # Raw IP.

    ARPHRD_TUNNEL = 768  # IPIP tunnel.
    ARPHRD_TUNNEL6 = 769  # IPIP6 tunnel.
    ARPHRD_FRAD = 770  # Frame Relay Access Device.
    ARPHRD_SKIP = 771  # SKIP vif.
    ARPHRD_LOOPBACK = 772  # Loopback device.
    ARPHRD_LOCALTLK = 773  # Localtalk device.
    ARPHRD_FDDI = 774  # Fiber Distributed Data Interface.
    ARPHRD_BIF = 775  # AP1000 BIF.
    ARPHRD_SIT = 776  # sit0 device - IPv6-in-IPv4.
    ARPHRD_IPDDP = 777  # IP-in-DDP tunnel.
    ARPHRD_IPGRE = 778  # GRE over IP.
    ARPHRD_PIMREG = 779  # PIMSM register interface.
    ARPHRD_HIPPI = 780  # High Performance Parallel I'face.
    ARPHRD_ASH = 781  # (Nexus Electronics) Ash.
    ARPHRD_ECONET = 782  # Acorn Econet.
    ARPHRD_IRDA = 783  # Linux-IrDA.
    ARPHRD_FCPP = 784  # Point to point fibrechanel.
    ARPHRD_FCAL = 785  # Fibrechanel arbitrated loop.
    ARPHRD_FCPL = 786  # Fibrechanel public loop.
    ARPHRD_FCFABRIC = 787  # Fibrechanel fabric.
    ARPHRD_IEEE802_TR = 800  # Magic type ident for TR.
    ARPHRD_IEEE80211 = 801  # IEEE 802.11.
    ARPHRD_IEEE80211_PRISM = 802  # IEEE 802.11 + Prism2 header.
    ARPHRD_IEEE80211_RADIOTAP = 803  # IEEE 802.11 + radiotap header.
    ARPHRD_IEEE802154 = 804  # IEEE 802.15.4 header.
    ARPHRD_IEEE802154_PHY = 805  # IEEE 802.15.4 PHY header.
    ARPHRD_NONE = 0xFFFE  # Zero header length.


class MacAddress:

    def __init__(self, hwaddr: int):
        self.address = hwaddr

    def __str__(self):
        return format(self.address, "012X")

    def __int__(self):
        return self.address


class Interface:
    """Represents a network interface on the local host.
    """

    SIOCGIFNAME = 0x8910
    SIOCGIFCONF = 0x8912
    SIOCGIFFLAGS = 0x8913
    SIOCGIFADDR = 0x8915
    SIOCGIFBRDADDR = 0x8919
    SIOCGIFNETMASK = 0x891b
    SIOCGIFHWADDR = 0x8927
    SIOCGIFCOUNT = 0x8938

    # Flags from SIOCGIFFLAGS
    IFF_UP = 0x1  # Interface is up.
    IFF_BROADCAST = 0x2  # Broadcast address valid.
    IFF_DEBUG = 0x4  # Turn on debugging.
    IFF_LOOPBACK = 0x8  # Is a loopback net.
    IFF_POINTOPOINT = 0x10  # Interface is point-to-point link.
    IFF_NOTRAILERS = 0x20  # Avoid use of trailers.
    IFF_RUNNING = 0x40  # Resources allocated.
    IFF_NOARP = 0x80  # No address resolution protocol.
    IFF_PROMISC = 0x100  # Receive all packets.
    IFF_ALLMULTI = 0x200  # Receive all multicast packets.
    IFF_MASTER = 0x400  # Master of a load balancer.
    IFF_SLAVE = 0x800  # Slave of a load balancer.
    IFF_MULTICAST = 0x1000  # Supports multicast.
    IFF_PORTSEL = 0x2000  # Can set media type.
    IFF_AUTOMEDIA = 0x4000  # Auto media select active.

    def __init__(self, name, index=None):
        self.name = name
        self.index = index
        self._sock = None
        self._fd = -1

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name!r}, {self.index!r})"

    def __str__(self):
        return f"{self.name}({self.index})"

    def __del__(self):
        self.close()

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            self._fd = -1

    def _open_sock(self):
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._fd = self._sock.fileno()

    def _get_buffer(self):
        self._open_sock()
        buf = bytearray(32)
        bname = self.name.encode("ascii")
        buf[:len(bname)] = bname
        return buf

    def _get_flags(self):
        buf = self._get_buffer()
        ioctl(self._fd, Interface.SIOCGIFFLAGS, buf)
        return int.from_bytes(buf[16:18], byteorder=sys.byteorder)

    @property
    def ip_address(self):
        """Get the IPv4 address of this interface."""
        buf = self._get_buffer()
        try:
            ioctl(self._fd, Interface.SIOCGIFADDR, buf)
        except OSError:
            return None
        addr = socket.inet_ntoa(buf[20:24])
        ioctl(self._fd, Interface.SIOCGIFNETMASK, buf)
        mask = socket.inet_ntoa(buf[20:24])
        return ipaddress.IPv4Interface("{}/{}".format(addr, mask))

    @property
    def hw_address(self):
        """Get the hardware address of this interface."""
        buf = self._get_buffer()
        try:
            ioctl(self._fd, Interface.SIOCGIFHWADDR, buf)
        except OSError:
            return None
        family = AddressFamily(int.from_bytes(buf[16:18], byteorder=sys.byteorder))
        if family == AddressFamily.ARPHRD_ETHER:
            hwaddr = int.from_bytes(buf[18:24], byteorder="big")  # network byte order
            return MacAddress(hwaddr)
        return None

    @property
    def is_up(self):
        """True if interface is administratively up."""
        return bool(self._get_flags() & Interface.IFF_UP)

    @property
    def is_loopback(self):
        """True if a loopback interface."""
        return bool(self._get_flags() & Interface.IFF_LOOPBACK)

    @property
    def is_pointtopoint(self):
        """True if a point-to-point link."""
        return bool(self._get_flags() & Interface.IFF_POINTOPOINT)

    @property
    def is_running(self):
        """True if resources allocated for running."""
        return bool(self._get_flags() & Interface.IFF_RUNNING)

    @property
    def is_promiscuous(self):
        """True if interface in promiscuous mode."""
        return bool(self._get_flags() & Interface.IFF_PROMISC)


def get_all_interfaces() -> List[Interface]:
    """Get all network interfaces on system."""
    rv = []
    for index, name in socket.if_nameindex():
        rv.append(Interface(name, index))
    return rv


def find_interface(name) -> Union[None, Interface]:
    """Return an Interface object from interface name.

    Return None if not found.
    """
    try:
        index = socket.if_nametoindex(name)
    except OSError:
        return None
    return Interface(name, index)


if __name__ == "__main__":
    # self-tests:
    for iface in get_all_interfaces():
        print(iface.name)
        print("  IP address:", iface.ip_address)
        print("  is up?", iface.is_up)
        print("  HW address:", iface.hw_address)
        print()
