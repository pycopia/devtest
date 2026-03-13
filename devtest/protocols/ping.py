"""Verify host reachability, discover hosts, and verify host reboots using ICMP ECHO.

Requires the *fping* program to be installed.
"""
from __future__ import annotations

from typing import Callable, Optional
import ipaddress
import socket

from devtest.typing import RunnerTypeBytes, RunnerOutBytes
from devtest import timers
from devtest.os import process
from devtest.os.procutils import which

FPING = which("fping")
if FPING is None:
    raise ImportError(f"{__name__} requires fping program installed.")


class Error(Exception):
    pass


class RebootDetectorError(Error):
    """Raised when the RebootDetector cannot verify a reboot."""


def _default_runner(cmd: str) -> RunnerOutBytes:
    pm = process.get_manager()
    return pm.run_command(cmd)


def _make_address(target):
    try:
        return ipaddress.ip_address(target)  # validates
    except ValueError:  # probably a name, look it up.
        for family, sotype, proto, canonname, sockaddr in socket.getaddrinfo(target, None):
            return ipaddress.ip_address(sockaddr[0])
    raise ValueError(f"Could not convert {target} to IP address.")


class Pinger:

    def __init__(self,
                 runner: RunnerTypeBytes = _default_runner,
                 retries: int = 3,
                 timeout: float = 0.5,
                 size: int = 512,
                 hops: int = 30):
        self._cmd_base = (f"{FPING} --addr --retry={retries:d} --timeout={int(timeout * 1000):d}"
                          f"--size={size:d} --ttl={hops:d} --random")
        self._runner = runner

    def is_reachable(self, target: str):
        target = _make_address(target)
        cmd = f"{self._cmd_base} {target}"
        output, stderr, status = self._runner(cmd)
        if status and b"is alive" in output:
            return True
        return False

    def all_reachable(self, netstr: str):
        """Return a list of all reachable hosts on a given subnet."""
        returnvalue = []
        net = ipaddress.ip_network(netstr, strict=True)  # validates
        cmd = f"{self._cmd_base} --alive -g {net}"
        output, stderr, status = self._runner(cmd)
        for line in output.splitlines():
            addr = ipaddress.ip_address(line.decode("ascii"))
            returnvalue.append(addr)
        return returnvalue


class RebootDetector:
    """Detect a reboot of a remote device using "ping".

    The following algorithm is used:

    1. Verify the target is pingable.
    1a. Optionally call the rebooter function to initiate the reboot.
        Without this, it is assumed the target started reboot just prior to calling go method.
    2. Loop until target is not pingable.
    3. While target is not pingable, loop until it is pingable again.

    The target must have recently initiated a reboot before this is called, and
    still be pingable. Timing is important in this case. Better to supply a rebooter function.

    May raise RebootDetectorError at any phase.
    """
    UNKNOWN = 0
    REACHABLE = 1
    NOTREACHABLE = 2
    REACHABLE2 = 3

    def __init__(self,
                 target: str,
                 runner: RunnerTypeBytes = _default_runner,
                 poll_interval: float = 2.0,
                 retries: int = 3,
                 timeout: float = 0.5,
                 size: int = 512,
                 hops: int = 30):
        self._target = target
        self._poll_interval = float(poll_interval)
        self._pinger = Pinger(runner=runner, retries=retries, timeout=timeout, size=size, hops=hops)

    def go(self, rebooter: Optional[Callable] = None):
        """Start the reboot detection.

        If a *rebooter* callback is provided it is called after verifying that target is reachable
        initially.

        Returns a boolean value indicating success.

        May raise RebootDetectorError if something is not right with the reboot process.
        """
        isreachable = False
        pinger = self._pinger
        state = RebootDetector.UNKNOWN
        while True:
            if state == RebootDetector.UNKNOWN:
                isreachable = pinger.is_reachable(self._target)
                if isreachable:
                    state = RebootDetector.REACHABLE
                    if rebooter is not None:
                        rebooter()
                else:
                    raise RebootDetectorError("Could not reach host initially.")
            elif state == RebootDetector.REACHABLE:
                r_retries = 30
                while isreachable:
                    timers.nanosleep(self._poll_interval)
                    r_retries -= 1
                    if r_retries < 0:
                        raise RebootDetectorError("Target did not become unreachable.")
                    isreachable = pinger.is_reachable(self._target)
                else:
                    state = RebootDetector.NOTREACHABLE
            elif state == RebootDetector.NOTREACHABLE:
                r_retries = 30
                while not isreachable:
                    timers.nanosleep(self._poll_interval)
                    r_retries -= 1
                    if r_retries < 0:
                        raise RebootDetectorError("Target did not become reachable again.")
                    isreachable = pinger.is_reachable(self._target)
                else:
                    state = RebootDetector.REACHABLE2
                    break
        return state == RebootDetector.REACHABLE2

    def verify_reboot(self, rebooter: Optional[Callable] = None) -> bool:
        """Simple verify function not requiring exception handling.

        Like the `go` method, but doesn't raise an excepton, Instead, it
        only returns a boolean value indication reboot operation success.
        """
        try:
            return self.go(rebooter)
        except RebootDetectorError:
            return False


def verify_reboot(target: str,
                  rebooter: Optional[Callable] = None,
                  runner: RunnerTypeBytes = _default_runner,
                  poll_interval: float = 2.0,
                  retries: int = 3,
                  timeout: float = 0.5,
                  size: int = 512,
                  hops: int = 30):
    """Verify that target host reboots."""

    rbt = RebootDetector(target,
                         runner=runner,
                         poll_interval=poll_interval,
                         retries=retries,
                         timeout=timeout,
                         size=size,
                         hops=hops)
    return rbt.verify_reboot(rebooter)


def main(argv):
    """Run pinger as main program. Primarily used for testing it.
    """
    target = argv[1] if len(argv) > 1 else "localhost"
    pinger = Pinger()
    if pinger.is_reachable(target):
        print(f"{target} reachable.")
    else:
        print(f"{target} NOT reachable.")


if __name__ == "__main__":
    import sys

    main(sys.argv)
