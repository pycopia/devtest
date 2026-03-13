"""A host controller for running with async frameworks.

Objects here operate with a collection of host controllers.
"""
from __future__ import annotations
# mypy: disable_error_code=override

import os
import signal
from collections import namedtuple
from typing import Tuple, Optional, Union, List, TypeVar, Generic, cast

from devtest.typing import StringOrBytes
from devtest import timers
from devtest.io import reactor
from devtest.os import exitstatus
from devtest.protocols import ssh
from devtest.qa import signals

from .hostcontroller import HostControllerError, LinuxController

RV = TypeVar("RV", str, bytes, exitstatus.ExitStatus)


class MultiOutput(list, Generic[RV]):
    """Sequence object with some of the same methods as bytes, str, and ExitStatus.

    The methods operate on all contained objects.
    """

    def __bool__(self):
        return all(bool(o) for o in self)

    def decode(self, encoding: str = "utf-8", errors: str = "strict") -> List[str]:
        return [s.decode(encoding, errors) for s in self]

    def strip(self, chars: Optional[Union[str, bytes]] = None) -> List[Union[str, bytes]]:
        return [s.strip(chars) for s in self]


HostInfo = namedtuple("HostInfo", [
    'ip', 'user', 'pw', 'private_key', 'public_key', 'proxy_ip', 'proxy_user', 'proxy_pw',
    'proxy_private_key', 'proxy_public_key'
],
                      defaults=[None] * 10)  # type: ignore


class MultiController(LinuxController):

    def initialize(self):
        super().initialize()
        self._equipmentlist = None

    @classmethod
    def from_equipmentlist(cls, eqlist):
        return NotImplemented

    def run_command(self,
                    command: str,
                    input: Optional[StringOrBytes] = None,
                    use_pty: bool = False,
                    timeout: Optional[float] = None,
                    environment: Optional[dict] = None,
                    elevated: bool = False,
                    encoding: Optional[str] = "utf8") -> MultiOutput:
        """Run a command on all devices.

        Args:
            command:  The command line to run.
            input: input to the command, if any.
            use_pty: allocate a pty on device.
            timeout: Task timeout of remote process.
            environment: Additional environment variables for process.
            elevated: run with elevated permissions using **sudo**. Assumes no password required.
            encoding: text encoding for command IO. If None, use bytes.

        Returns:
            A list of the stdout as text, or bytes if encoding=None.

        Raises:
            HostControllerError if command returned abnormally.
            TimeoutError if timeout time reached before command completes.
        """

        if elevated:
            command = "sudo " + command
        if input is not None:
            if encoding is not None:
                input = cast(str, input)  # make mypy happy
                inp = input.encode(encoding)
            elif not isinstance(input, bytes):
                raise ValueError("input must be bytes, or str with encoding.")
            else:
                inp = input
        else:
            inp = None
        # With older sshd (7.x) you must also use a pty to get a timeout.
        # This means that line endings of text will be different.
        self._log.debug(f"run_command: {command!r}")
        if timeout is not None:

            def _timeout(sig, stack):
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
                raise TimeoutError(f"running: {command!r}")

            signal.signal(signal.SIGALRM, _timeout)
            timers.alarm(float(timeout))
        try:
            out, err, exitstatus = self._run_command(command,
                                                     input=inp,
                                                     use_pty=use_pty,
                                                     environment=environment)
        except TimeoutError:
            self.close()  # forces remote process to quit
            raise
        finally:
            if timeout is not None:
                timers.alarm(0.0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
        if not exitstatus:
            raise HostControllerError(f"Failed to run: {command}", err)
        if encoding is None:
            return cast(MultiOutput[bytes], out)
        else:
            return cast(MultiOutput[str], out.decode(encoding))


class MultiSSHController(MultiController):
    """Wraps a list of controllers that use the SSH module.

    Methods here operate on all contained devices simultaneously.
    """

    @classmethod
    def from_equipmentlist(cls, eqlist):
        new = cls(eqlist[0])  # base class wants single equipment.
        new._equipmentlist = eqlist[:]
        new.name = ", ".join(eq.name for eq in eqlist)
        for host in eqlist:
            host._aclient = ssh.AsyncSSHClient()
            ip = str(host.primary_interface.ipaddr.ip)
            if host.parent:
                proxy = host.parent
                proxy_ip = str(proxy.primary_interface.ipaddr.ip)
                proxy_user = proxy["login"]
                proxy_pw = proxy["password"]
                proxy_private_key = proxy["private_key"]
                proxy_public_key = proxy["public_key"]
            else:
                proxy_ip = None
                proxy_user = None
                proxy_pw = None
                proxy_private_key = None
                proxy_public_key = None
            host.hostinfo = HostInfo(ip, host["login"], host["password"], host["private_key"],
                                     host["public_key"], proxy_ip, proxy_user, proxy_pw,
                                     proxy_private_key, proxy_public_key)
            host.local_address = None
        return new

    async def _aconnect(self):
        for host in self._equipmentlist:
            client = host._aclient
            if client.closed:
                hostinfo = host.hostinfo
                if hostinfo.proxy_ip is None:  # No proxy, so use direct connection.
                    address = (hostinfo.ip, 22)
                else:
                    for responder, address in signals.service_want.send(
                            host,
                            service="sshtunnel",
                            proxy_address=(hostinfo.proxy_ip, 22),
                            proxy_user=hostinfo.proxy_user,
                            proxy_password=hostinfo.proxy_pw,
                            proxy_private_key=hostinfo.proxy_private_key,
                            proxy_public_key=hostinfo.proxy_public_key,
                            ssh_passphrase=host["ssh_passphrase"]):
                        if address is not None:
                            break
                    else:
                        raise HostControllerError(f"SSH tunnel didn't happen for {host.name}.")
                    host.local_address = address

                await client.connect(address,
                                     hostinfo.user,
                                     password=hostinfo.pw,
                                     private_key=hostinfo.private_key,
                                     public_key=hostinfo.public_key,
                                     passphrase=host["ssh_passphrase"])

    async def _aclose(self):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(host._aclient.close())
        return tg.results

    async def _aread_file(self, path, encoding):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(host._aclient.read_file(path))
        if encoding:
            return [s.decode(encoding) for s in tg.results]
        else:
            return tg.results

    async def _awrite_file(self, path, data, permissions):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(host._aclient.write_file(path, data, permissions=permissions))
        return tg.results

    async def _unlink(self, path):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(host._aclient.unlink(path))
        return tg.results

    async def _rename(self, source, destination):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(host._aclient.rename(source, destination))
        return tg.results

    async def _arun_command(self, command, input=None, use_pty=False, environment=None):
        async with reactor.TaskGroup() as tg:
            for host in self._equipmentlist:
                await tg.spawn(
                    host._aclient.run_command(command,
                                              input=input,
                                              use_pty=use_pty,
                                              environment=environment))
        return tg.results

    def _connect(self):
        kern = reactor.get_kernel()
        return kern.run(self._aconnect())

    def _run_command(
        self,
        command: str,
        input: Optional[bytes] = None,
        use_pty: bool = False,
        environment: Optional[dict] = None
    ) -> Tuple[MultiOutput[bytes], MultiOutput[bytes], MultiOutput[exitstatus.ExitStatus]]:
        # A quirk in the Curio system requires the results iterator be fully consumed in order for
        # the network connnects to shut down properly. So return a fully realized list so the
        # results objects and coroutines can be dereferenced, and closed, here.
        self._connect()
        outputs = cast(MultiOutput[bytes], MultiOutput())
        errs = cast(MultiOutput[bytes], MultiOutput())
        statuses = cast(MultiOutput[exitstatus.ExitStatus], MultiOutput())
        kern = reactor.get_kernel()
        results = kern.run(self._arun_command(command, input, use_pty, environment))
        for output, err, status in results:
            if not status:
                raise HostControllerError(err)
            outputs.append(output)
            errs.append(err)
            statuses.append(status)
        return outputs, errs, statuses

    def close(self):
        kern = reactor.get_kernel()
        kern.run(self._aclose())
        super().close()
        for host in self._equipmentlist:
            if host.local_address is not None:
                signals.service_dontwant.send(host,
                                              service="sshtunnel",
                                              local_port=host.local_address[1])
            host.local_address = None

    def _read_file(self, path, encoding):
        self._connect()
        kern = reactor.get_kernel()
        return kern.run(self._aread_file(path, encoding))

    def _write_file(self, path, data, encoding=None, permissions=None):
        self._connect()
        if encoding:
            data = data.encode(encoding)
        kern = reactor.get_kernel()
        return kern.run(self._awrite_file(path, data, permissions))

    def unlink(self, path):
        self._connect()
        kern = reactor.get_kernel()
        return kern.run(self._unlink(str(path)))

    def rename(self, source, destination):
        self._connect()
        kern = reactor.get_kernel()
        return kern.run(self._rename(str(source), str(destination)))

    def _spawn_command(self,
                       command: str,
                       use_pty: bool = False,
                       environment: Optional[dict] = None):
        raise NotImplementedError("override me!")

    def copy_to(self, source: Union[os.PathLike, str], destination: Union[os.PathLike, str]):
        """Copy file from local source to remote destination.
        """
        raise NotImplementedError("override me!")

    def copy_from(self, remote: Union[os.PathLike, str], local: Union[os.PathLike, str]):
        """copy file from remote path to local file.
        """
        raise NotImplementedError("override me!")

    def listdir(self,
                path: Union[os.PathLike, str],
                glob: Optional[str] = None,
                encoding: str = "utf8"):
        """List a directory on VPU.

        Yields:
            List of Tuple of name and StatResult
        """
        raise NotImplementedError("override me!")
