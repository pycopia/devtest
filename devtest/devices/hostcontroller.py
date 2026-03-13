"""Generic controller for all hosts that run Linux.
"""

import signal
from typing import Any, Dict, List, Tuple, AnyStr, Optional, Union, Callable, Generator, cast
from functools import partial
from datetime import datetime
from textwrap import dedent
from inspect import isfunction, getsource

from devtest import logging
from devtest.physics.physical_quantities import PhysicalQuantity
from devtest.typing import StringOrBytes, AnyPath

from devtest import timers
from devtest import json
from devtest.core import exceptions
from devtest.core import constants
from devtest.os import commands
from devtest.os import filesystem
from devtest.os import exitstatus
from devtest.devices import Controller
from devtest.protocols import ping


class HostControllerError(exceptions.ControllerError):
    """Raised on errors in an host controller."""


class SpawnedProcess:
    """A running process managed by systemd.

    Returned by controller methods.
    """

    def __init__(self, controller, identifier):
        self._controller = controller
        self._ident = identifier
        self._status = None

    def terminate(self):
        """Terminate remote process."""
        sysctl = SystemCtl(self._controller)
        return sysctl.stop(self._ident)

    def close(self):
        """Close the process. Same as terminating it."""
        self.terminate()

    @property
    def is_running(self):
        """True if this process is still in runnable, or active, state."""
        sysctl = SystemCtl(self._controller)
        return sysctl.is_active(self._ident)


class LinuxController(Controller):
    """Generic controller for all Linux based target systems.

    Assumes a more modern, systemd based Linux system.

    You must subclass and override the _run_command, and other, methods.
    """

    MULTI_CONTROLLER: Optional[str] = None

    def initialize(self):
        self._log = logging.get_logger(self._equipment.name)
        super().initialize()

    def finalize(self):
        super().finalize()
        if self._log is not None:
            self._log.close()
            self._log = None

    def _run_command(
            self,
            command: str,
            input: Optional[bytes] = None,
            use_pty: bool = False,
            timeout: Optional[float] = None,
            environment: Optional[dict] = None) -> Tuple[bytes, bytes, exitstatus.ExitStatus]:
        raise NotImplementedError("override me!")

    def _connect(self):
        raise NotImplementedError("override me!")

    def _spawn_command(self,
                       command: str,
                       use_pty: bool = False,
                       environment: Optional[dict] = None) -> SpawnedProcess:
        raise NotImplementedError("override me!")

    def _read_file(self, path: AnyPath, encoding: Optional[str]) -> Union[str, bytes]:
        raise NotImplementedError("override me!")

    def _write_file(self,
                    path: AnyPath,
                    data: Union[str, bytes],
                    encoding: Optional[str],
                    permissions: Optional[int] = None) -> int:
        raise NotImplementedError("override me!")

    def copy_to(self, source: AnyPath, destination: AnyPath):
        """Copy file from local source to remote destination.
        """
        raise NotImplementedError("override me!")

    def copy_from(self, remote: AnyPath, local: AnyPath):
        """copy file from remote path to local file.
        """
        raise NotImplementedError("override me!")

    def unlink(self, remotefile: AnyPath):
        """Unlink (delete) the given path to a file.
        """
        raise NotImplementedError("override me!")

    def listdir(self,
                path: AnyPath,
                glob: Optional[str] = None,
                encoding: str = "utf8") -> Generator[Tuple[str, filesystem.StatResult], None, None]:
        """List a directory on device.

        Args:
            path: root directory to start searching from.
            glob: glob-style pattern to filter on.
            encoding: name of codec to decode path names. Default: utf8

        Yields:
            Tuple of name and StatResult
        """
        raise NotImplementedError("override me!")

    def run_command_async(self,
                          name: str,
                          command: str,
                          uid: int = 1000,
                          gid: int = 1000,
                          use_pty: bool = False,
                          environment: Optional[dict] = None):
        """Start a process running in the background.

        Uses systemd to manage the process.

        Returns:
            :ref:`SpawnedProcess` object.
        """
        pty = "--pty" if use_pty else ""
        cmd = (f'sudo systemd-run --uid {uid} --gid {gid} {pty} --remain-after-exit --collect '
               f'--unit="{name}" {command}')
        self.run_command(cmd, environment=environment)
        return SpawnedProcess(self, name)

    def run_command(self,
                    command: str,
                    input: Optional[StringOrBytes] = None,
                    use_pty: bool = False,
                    timeout: Optional[float] = None,
                    sockettimeout: Optional[float] = None,
                    environment: Optional[dict] = None,
                    elevated: bool = False,
                    encoding: Union[str, None] = "utf8") -> Union[str, bytes]:
        """Run a command on the device, with optional timeouts.

        Two types of timeouts are provided. The `sockettimeout` is a low-level timeout that may
        make the command exit prematurely. You may get incomplete output in that case.
        The `timeout` is a hard timeout and will raise TimeoutError exception when time is reached.

        Args:
            command:  The command line to run.
            input: input to the command, if any.
            use_pty: allocate a pty on device.
            timeout: Task timeout of remote process.
            sockettimeout: Max time, in seconds, to wait for blocking operation. This is socket
                           level timeout.
            environment: Additional environment variables for process.
            elevated: run with elevated permissions using **sudo**. Assumes no password required.
            encoding: text encoding for command IO. If None, use bytes.

        Returns:
            the stdout as text, or bytes if encoding=None.

        Raises:
            HostControllerError: if command returned abnormally. A non-zero exit status is abnormal.
            TimeoutError: if timeout time reached before command completes.
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
        if sockettimeout is not None:
            use_pty = True
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
                                                     timeout=sockettimeout,
                                                     environment=environment)
        except TimeoutError:
            self.close()  # forces remote process to quit
            raise
        except FileNotFoundError as exc:
            raise HostControllerError(f"Not found: {command}", str(exc)) from exc
        finally:
            if timeout is not None:
                timers.alarm(0.0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
        if not exitstatus:
            if int(exitstatus) == 127:  # shells indicate it can't find executable with this code.
                raise HostControllerError(f"Not found: {command}", err)
            else:
                raise HostControllerError(f"ran with error {int(exitstatus)}: {command}", err)
        if encoding is None:
            return cast(bytes, out)
        else:
            cast(bytes, out)
            return cast(str, out.decode(encoding))

    def run_python(self,
                   func: Callable,
                   *args,
                   timeout: Optional[float] = None,
                   elevated: bool = False,
                   debug: bool = False,
                   input: Optional[str] = None) -> Any:
        """Run a bit of Python code on the target device.

        You may run the python code with elevated privilege. Assumes python3 binary is on PATH.

        Args:
            func: A Python function. This will be copied to target as bare function and run there.
            \\*args: additional positional arguments are passed to the script's argument list.
            timeout: maximum time script is allowed to run, in seconds.
            elevated: Run with elevated permissions with **sudo**.
            debug: Preserve the generated script on the device.
            input: optional input to send to the script, if it requires it.

        Returns:
            stdout of the script.
        """
        if not isfunction(func):
            raise ValueError("First argument must be callable function.")
        code = dedent(getsource(func))
        script = f'\nimport sys\n\n{code}\n\nsys.exit({func.__name__}(*sys.argv[1:]))\n'
        filename = f"/tmp/run_python{id(func)}.py"
        command = f'python3 {filename} {" ".join(str(o) for o in args)}'
        self.write_file(filename, script)
        try:
            output = self.run_command(command, input=input, timeout=timeout, elevated=elevated)
        finally:
            if not debug:
                self.unlink(filename)
        return output

    def read_file(self, path: AnyPath, encoding: Optional[str] = "utf8") -> Union[str, bytes]:
        """Get the content of a file on device."""
        return self._read_file(path, encoding)

    def write_file(self,
                   path: AnyPath,
                   data: AnyStr,
                   encoding: Optional[str] = "utf8",
                   permissions: Optional[int] = None) -> int:
        """Write a string directly to a file on device.

        Args:
            path: target path name.
            data: chunk of test to write. Should be bytes object if encoding is None.
            encoding: If data is text, use this encoding.
            permissions: File mode/permissions to set file to.

        Returns:
            Number of bytes actually written.
        """
        return self._write_file(path, data, encoding, permissions=permissions)

    def statvfs(self, path: str = "/") -> filesystem.StatVfsResult:
        """Get information for a file system.

        Args:
            path: the path to get the usage of.

        Returns:
            StatVfsResult
        """
        return commands.StatVfs(path).run_with(cast(Callable[[str], str], self.run_command))

    def stat(self, path: str) -> filesystem.StatResult:
        """Get information about an object in the file system.

        Args:
            path: the path to the object (file, directory, whatever).

        Returns:
            StatResult
        """
        return commands.Stat(path).run_with(cast(Callable[[str], str], self.run_command))

    def exists(self, path):
        """Check if the path exists.

        Args:
            path: the path to the object (file, directory).

        Returns:
            Boolean value
        """
        try:
            commands.Stat(path).run_with(self.run_command)
            return True
        except HostControllerError:
            return False

    @property
    def uptime(self):
        """The system uptime (walltime), as PhysicalQuantity (seconds)."""
        timetext = cast(str, self.read_file("/proc/uptime"))
        walltime, cpuidle = timetext.split()
        return PhysicalQuantity(float(walltime), "s")

    @property
    def uptime_monotonic(self):
        """The system monotonic uptime, as PhysicalQuantity (ns)."""
        # Seems to be the best way to get this without a helper program.
        timer_list = self.run_command("sudo head -n 3 /proc/timer_list", encoding=None)
        start = timer_list.find(b"now at ") + 7
        nsecs = float(timer_list[start:timer_list.find(b" ", start)])
        return PhysicalQuantity(nsecs, "ns")

    def reboot(self):
        """Reboot this host."""
        rebooter = partial(self.run_command, "sudo reboot")
        return ping.verify_reboot(self._equipment["hostname"], rebooter=rebooter)

    @property
    def systemctl(self):
        """Acccess systemctl controller."""
        return SystemCtl(self)

    @property
    def journalctl(self):
        """Acccess journal controller."""
        return JournalCtl(self)

    @property
    def cpuinfo(self) -> Dict[int, Dict[str, str]]:
        """CPU info from /proc/cpuinfo"""
        processors: Dict[int, Dict[str, str]] = {}
        currentproc: Dict[str, str]
        cpuinfo = cast(str, self.read_file("/proc/cpuinfo"))
        for line in cpuinfo.splitlines():
            if line.startswith("processor"):
                _, index = line.split(":")
                processors[int(index)] = currentproc = {}
            else:
                if line and len(parts := line.split(":", 1)) >= 2:
                    currentproc[parts[0].strip()] = parts[1].strip()
        return processors

    @property
    def interrupts(self) -> Dict[str, Tuple[List[int], str]]:
        """Interrupt counts from /proc/interrupts."""
        interruptdata: Dict[str, Tuple[List[int], str]] = {}
        ncpus = 1
        interrupts = cast(str, self.read_file("/proc/interrupts"))
        for line in interrupts.splitlines():
            if ":" not in line:  # first line only, with CPUx
                cpus = line.split()
                ncpus = len(cpus)
            else:
                irqname, rest = line.split(":", 1)
                interparts = rest.split(None, ncpus)
                interruptdata[irqname.strip()] = ([int(n) for n in interparts[:ncpus]],
                                                  " ".join(interparts[ncpus:]))
        return interruptdata

    @property
    def cmdline(self) -> dict:
        """The Linux kernel command line.

        This is a dictionary of kernel command line options.
        The value part will be None if not a key-value pair.
        """
        linux_cmdline = {}
        cmdline = cast(str, self.read_file("/proc/cmdline"))
        for part in cmdline.split():
            l, _, r = part.partition("=")
            linux_cmdline[l] = r or None
        return linux_cmdline

    @property
    def interfaces(self):
        """All defined interfaces."""
        return self.get_interfaces()

    @property
    def ethernet_interfaces(self):
        """All connected Ethernet interfaces."""
        return self.get_interfaces(iftype=constants.NetworkType.Ethernet)

    @property
    def can_interfaces(self):
        """All connected CAN interfaces."""
        # CAN interfaces are of type Other since there is no IANA defined number for them.
        return self.get_interfaces(iftype=constants.NetworkType.Other)

    def get_interface(self, ifname):
        """Get an interface controller by interface name.

        Returns:
            InterfaceController for named interface, or None if not found.
        """
        eqr = self._equipment.get_interface_by_name(ifname)
        if eqr:
            return InterfaceController(eqr, self)
        else:
            return None

    def get_interfaces(self, iftype: Optional[constants.NetworkType] = None):
        """All interfaces, or all attached interfaces of a particular type."""
        self._connect()
        eq = self._equipment
        if iftype is None:
            return [InterfaceController(iface, self) for iface in eq.interfaces]
        else:
            return [
                InterfaceController(iface, self)
                for iface in eq.interfaces
                if iface.network and iface.network.type == iftype
            ]


class InterfaceController(Controller):
    """Active controller for device specific interface."""

    def __init__(self, interface, hostcontroller):
        super().__init__(interface)
        self._controller = hostcontroller

    def initialize(self):
        self.name = self._equipment.name

    def up(self):
        """Set interface administratively UP."""
        cmd = f"sudo ip link set {self._equipment.name} up"
        return self._controller.run_command(cmd)

    def down(self):
        """Set interface administratively DOWN."""
        cmd = f"sudo ip link set {self._equipment.name} down"
        return self._controller.run_command(cmd)

    def status(self):
        """Dictionary of interface status.
        """
        cmd = f"sudo ip -j link show {self._equipment.name}"
        text = self._controller.run_command(cmd)
        return json.decode(text)[0]

    @property
    def is_up(self):
        """True if interface is both UP and adminstratively up.
        """
        status = self.status()
        flags = status["flags"]
        return "UP" in flags and "LOWER_UP" in flags

    @property
    def is_down(self):
        """True if interface is down.
        """
        return not self.is_up

    @property
    def statistics(self):
        """Dictionary of interface statistics.
        """
        cmd = f"sudo ip -j -d -s -s link show {self._equipment.name}"
        text = self._controller.run_command(cmd)
        return json.decode(text)[0]

    @property
    def ipv4address(self):
        """Configured IP v4 address of this interface."""
        return self._equipment.ipv4address


class SystemCtl:
    """Interface to systemd on system.

    Control and inspect systemd services for system and current user. Create and run service units
    to simplify perisistent remote process control.

    Args:
        controller: LinuxController to operate on. May be a multi-host controller.
    """

    _USER_SYSTEMD_LIB = "{home}/.config/systemd/user/"

    def __init__(self, controller: LinuxController):
        self._controller = controller
        home = self._controller.run_command("printenv HOME", encoding=None).strip()
        if isinstance(home, list):  # multihost support.
            home = home[0]
        self.user_system_lib = SystemCtl._USER_SYSTEMD_LIB.format(
            home=cast(bytes, home).decode("ascii"))

    def _systemctl(self, cmd, args, user):
        useropt = "--user" if user else ""
        sudo = "sudo" if not user else ""
        return self._controller.run_command(
            f"{sudo} systemctl --no-pager "
            f"-q {useropt} {cmd} {args}", encoding="ascii")

    def stop(self, *names, user: bool = False):
        """Stop one or more services."""
        self._systemctl("stop", ' '.join(names), user)

    def start(self, *names, user: bool = False):
        """Start one or more services."""
        self._systemctl("start", ' '.join(names), user)

    def info(self, name: str, user: bool = False) -> Union[dict, list]:
        """Return a dictionary of systemd information about the named service.

        This contains all available unit information. You are probably most interested in the
        following keys:

        - ActiveState: will be "active" if running, or "inactive".
        - SubState: will be "running" if running, or "dead".
        - MainPID: will be the PID, as a string. This will be '0' if SubState is "dead".

        Returns:
            dictionary of all system unit information.
        """
        out = self._systemctl("show", name, user)
        if isinstance(out, list):  # multihost support.
            return [self._parse_info(txt) for txt in out]
        else:
            return self._parse_info(out)

    def _parse_info(self, infotext):
        info = {}
        for line in infotext.splitlines():
            name, _, val = line.partition("=")
            info[name] = val.strip()
        return info

    def restart(self, *names, user: bool = False):
        """Restart one or more services."""
        self._systemctl("restart", ' '.join(names), user)

    def enable(self, *names, user: bool = False):
        """Enable one or more services."""
        return self._systemctl("enable", ' '.join(names), user)

    def disable(self, *names, user: bool = False):
        """Disable one or more services."""
        return self._systemctl("disable", ' '.join(names), user)

    def is_active(self, name: str, user: bool = False) -> bool:
        """Check that a named service is active."""
        try:
            self._systemctl("is-active", name, user)
        except HostControllerError:
            return False
        else:
            return True

    def is_enabled(self, name: str, user: bool = False) -> bool:
        """Check that a service is enabled."""
        try:
            self._systemctl("is-enabled", name, user)
        except HostControllerError:
            return False
        else:
            return True

    def create_service(self,
                       name: str,
                       command: str,
                       description: Optional[str] = None,
                       restartable: bool = False):
        """Create a user-private systemd service config.

        Args:
            name: unique name for the service.
            command: shell command line to run.
            description: Optional long description of the service.
            restartable: If True, make the service restart on failure.
        """
        if description is None:
            description = f"Run {command}"
        self._controller.run_command(f"mkdir -p {self.user_system_lib}")
        fname = f"{self.user_system_lib}/{name}.service"
        service_restart, prefix = ("on-failure", "") if restartable else ("no", "-")
        command = command.replace("'", r"\'")
        unit = (f"[Unit]\n"
                f"Description={description}\n\n"
                f"[Service]\n"
                f"Restart={service_restart}\n"
                f"ExecStart={prefix}/bin/bash -c '{command}'\n")
        self._controller._log.debug(f"create_service: {name}: {unit!r}")
        self._controller.write_file(fname, unit)
        self._controller.run_command("systemctl --user daemon-reload")

    def remove_service(self, name: str):
        """Remove a previously created user-private service.

        Args:
            name: identifier, same one used for create_service call.
        """
        fname = f"{self.user_system_lib}/{name}.service"
        self._controller.unlink(fname)
        self._controller.run_command("systemctl --user daemon-reload")

    def spawn_command(self,
                      name: str,
                      command: str,
                      description: Optional[str] = None,
                      restartable: bool = False,
                      check_delay: float = 0.5):
        """Spawn a command using systemd.

        The command will continue to run under control of systemd, user service manager. This
        creates a user service file and starts it. The name is any identifier. Use the same name to
        stop it later. The other :py:class:`SystemCtl` methods, such as ``stop`` and ``info``, must
        supply ``user=True`` since this is now a user-private service.

        Args:
            name: Name of the unit file and service. Use this same name to stop it later.
            command: shell command line to run.
            description: Optional description string.
            restartable: If True, create a service that automatically restarts on failure.
            check_delay: time, in seconds, to wait after starting to check that it did start.
        """
        self.create_service(name, command, description, restartable)
        self.start(name, user=True)
        timers.nanosleep(check_delay)
        if not self.is_active(name, user=True):
            raise HostControllerError(f"Failed to spawn: {command!r}")


class JournalCtl:
    """Interface to the system journal.

    Various control and query methods on the system's journal.

    Args:
        controller: LinuxController to operate on. May be a multi-host controller.
    """

    def __init__(self, controller: LinuxController):
        self._controller = controller

    def get_time_span(self, starttime: datetime, endtime: datetime, priority: str = "debug"):
        """Get system logs in the specified time span.

        Assumes password-less sudo.

        Args:
            starttime: beginning of time slice, as UTC time.
            endtime: end of time slice, as UTC time.
            priority: journal priority name to filter by priority.
        """
        cmd = (f'sudo journalctl -o short-unix '
               f'-S @{int(starttime.timestamp())} -U @{int(endtime.timestamp())} '
               f'--priority={priority} --no-pager --utc')
        return self._controller.run_command(cmd,
                                            input=None,
                                            use_pty=False,
                                            environment=None,
                                            encoding=None,
                                            timeout=60.0)

    def last_boot(self):
        """Show kernel messages for last boot up.
        """
        cmd = "journalctl --no-pager --output=short-unix --dmesg"
        return self._controller.run_command(cmd,
                                            input=None,
                                            use_pty=False,
                                            environment=None,
                                            encoding=None,
                                            timeout=60.0)
