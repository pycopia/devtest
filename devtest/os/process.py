"""
Simple, asynchronous process spawner and manager.
"""

from __future__ import generator_stop

import sys
import os
import signal
import atexit
import multiprocessing

import psutil

from subprocess import (  # noqa
    CompletedProcess,
    SubprocessError,
    CalledProcessError,
    PIPE,
    STDOUT,
    DEVNULL,
    )

from devtest import logging
from devtest.textutils import shparser
from devtest.io import subprocess
from devtest.io import streams
from devtest.io import socket
from devtest.io.reactor import (get_kernel, sleep, spawn,
                                timeout_after, CancelledError, TaskTimeout)
from devtest.os import procutils
from devtest.os import exitstatus


class ManagerError(Exception):
    pass


class ProgramNotFound(ManagerError):
    pass


class Process(psutil.Process):

    def interrupt(self):
        try:
            self._send_signal(signal.SIGINT)
        except psutil.NoSuchProcess:
            pass


class PipeProcess(Process):
    """Wrapped Popen class that merges async methods and psutil methods.
    """

    def __init__(self, *args, **kwargs):
        self._popen = subprocess.Popen(*args, **kwargs)
        self._init(self._popen.pid, _ignore_nsp=True)

    def __dir__(self):
        return list(set(dir(PipeProcess) + dir(subprocess.Popen)))

    def __getattribute__(self, name):
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            try:
                return object.__getattribute__(self._popen, name)
            except AttributeError:
                raise AttributeError("{} has no attribute {!r}".format(
                    self.__class__.__name__, name))

    def poll(self):
        if self._popen._popen.returncode is None:
            pid, sts = os.waitpid(self.pid, os.WNOHANG)
            if pid == self.pid:
                self._popen._popen._handle_exitstatus(sts)
        return self._popen._popen.returncode

    @property
    def args(self):
        return self._popen._popen.args

    @property
    def returncode(self):
        return self._popen._popen.returncode

    @property
    def exitstatus(self):
        rc = self._popen._popen.returncode
        if rc is None:
            return None
        return exitstatus.ExitStatus(0, name=self.progname, returncode=rc)

    @property
    def wait(self):
        return self._popen.wait

    def syncwait(self):
        return get_kernel().run(self._popen.wait())

    def close(self):
        self.interrupt()

    async def communicate(self, input=b''):
        """
        Communicates with a subprocess.  input argument gives data to
        feed to the subprocess stdin stream.  Returns a tuple (stdout, stderr)
        corresponding to the process output.  If cancelled, the resulting
        cancellation exception has stdout_completed and stderr_completed
        attributes attached containing the bytes read so far.
        """
        stdout_task = await spawn(self.stdout.readall) if self.stdout else None
        stderr_task = await spawn(self.stderr.readall) if self.stderr else None
        try:
            if input:
                await self.stdin.write(input)
                await self.stdin.close()

            stdout = await stdout_task.join() if stdout_task else b''
            stderr = await stderr_task.join() if stderr_task else b''
            return (stdout, stderr)
        except CancelledError as err:
            if stdout_task:
                await stdout_task.cancel()
                err.stdout = stdout_task.next_exc.bytes_read
            else:
                err.stdout = b''

            if stderr_task:
                await stderr_task.cancel()
                err.stderr = stderr_task.next_exc.bytes_read
            else:
                err.stderr = b''
            raise

    # File-like methods for use by other modules.
    async def aread(self, amt=-1):
        await self.stdout.read(amt)

    async def awrite(self, data):
        await self.stdin.write(data)

    def fileno(self):
        return self.stdout.fileno()

    def read(self, amt=-1):
        return get_kernel().run(self.stdout.read(amt))

    def readline(self):
        return get_kernel().run(self.stdout.readline())

    def readlines(self):
        return get_kernel().run(self.stdout.readlines())

    def write(self, data):
        kern = get_kernel()
        rv = kern.run(self.stdin.write(data))
        kern.run(self.stdin.flush())
        return rv


# Co-process server commands
CMD_CALL = 1
CMD_EXIT = 2
CMD_PING = 3


class CoProcess(Process):
    def __init__(self, pid, conn):
        self._init(pid, _ignore_nsp=True)
        self._conn = conn

    def start(self, func, *args):
        return get_kernel().run(self._start, func, args)

    async def _start(self, func, args):
        msg = (CMD_CALL, func, args)
        try:
            await self._conn.send(msg)
            # resp, result = await self._conn.recv()
        except CancelledError:
            await self.close()
            raise

    def poll(self):
        pid, sts = os.waitpid(self.pid, os.WNOHANG)
        if pid == self.pid:
            return sts

    def wait(self):
        return get_kernel().run(self._wait)

    async def _wait(self):
        resp, result = await self._conn.recv()
        if resp:
            return result
        else:
            raise result

    def close(self):
        get_kernel().run(self._close)

    async def _close(self):
        msg = (CMD_EXIT, )
        await self._conn.send(msg)
        await self._conn.close()

    def ping(self):
        return get_kernel().run(self._ping)

    async def _ping(self):
        msg = (CMD_PING,)
        await self._conn.send(msg)
        resp, result = await self._conn.recv()
        if resp and result == "PONG":
            return True
        return False


def _fork_coprocess(cwd):
    mysock, childsock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    os.set_inheritable(childsock.fileno(), True)
    pid = os.fork()
    if pid == 0:  # child
        if cwd is not None:
            os.chdir(str(cwd))
        mysock._socket.close()
        del mysock
        childsock = childsock.as_stream()
        conn = streams.Connection(childsock, childsock)
        return pid, conn
    else:
        childsock._socket.close()
        del childsock
        mysock = mysock.as_stream()
        conn = streams.Connection(mysock, mysock)
        return pid, conn


def _coprocess_server(conn):
    kern = get_kernel()
    try:
        kern.run(_coprocess_server_coro, conn, shutdown=True)
    except KeyboardInterrupt:
        pass


async def _coprocess_server_coro(conn):
    while True:
        msg = await conn.recv()
        cmd = msg[0]
        if cmd == CMD_CALL:
            func, args = msg[1:]
            if isinstance(func, str):
                local_ns = {"args": args}
                global_ns = globals()
                try:
                    code = compile(func, "coprocess", "exec")
                    exec(code, global_ns, local_ns)
                except Exception as ex:  # noqa
                    await conn.send((False, ex))
                await conn.send((True, local_ns))
            else:
                try:
                    rv = func(*args)
                except SystemExit as ex:
                    await conn.send((False, ex))
                    await conn.close()
                    break
                except Exception as ex:  # noqa
                    await conn.send((False, ex))
                    break
                await conn.send((True, rv))
        elif cmd == CMD_EXIT:
            await conn.close()
            break
        elif cmd == CMD_PING:
            await conn.send((True, "PONG"))


def _close_stdin():
    if sys.stdin is None:
        return

    try:
        sys.stdin.close()
    except (OSError, ValueError):
        pass

    try:
        fd = os.open(os.devnull, os.O_RDONLY)
        try:
            sys.stdin = open(fd, closefd=False)
        except:
            os.close(fd)
            raise
    except (OSError, ValueError):
        pass


def _redirect(fd, name):
    newfd = os.open(name, os.O_WRONLY | os.O_TRUNC | os.O_CREAT | os.O_NOFOLLOW | os.O_SYNC,
                    mode=0o644)
    orig_fd = os.dup(fd)
    os.dup2(newfd, fd)
    os.close(newfd)
    return orig_fd


def _restore_stderr(oldfd):
    sys.stderr.flush()
    os.dup2(oldfd, 2)
    os.close(oldfd)


class ProcessManager:
    """Starts and keeps track of subprocesses.
    """

    def __init__(self):
        self._procs = {}
        self._zombies = {}
        self.splitter = shparser.get_command_splitter()
        signal.signal(signal.SIGCHLD, self._sigchild)

    def __str__(self):
        return "ProcessManager: pids: {}".format(", ".join(self._procs.keys()))

    def close(self):
        self.killall()
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        self.splitter = None

    @property
    def processes(self):
        return self._procs.values()

    def start(self, commandline, stdin=PIPE, stdout=PIPE, stderr=PIPE,
              directory=None, exit_handler=None):
        """Start a subprocess using pipes."""
        if isinstance(commandline, str):
            argv = self.splitter(commandline)
        elif isinstance(commandline, list):
            argv = commandline
        else:
            raise ValueError("start needs a command string or argv list.")
        progname = procutils.which(argv[0])
        if not progname:
            raise ProgramNotFound("{!r} not found.".format(progname))
        logging.notice("ProcessManager: trying: {}".format(argv))
        proc = PipeProcess(argv,
                           stdin=stdin,
                           stdout=stdout,
                           stderr=stderr,
                           cwd=directory,
                           shell=False)
        self._procs[proc.pid] = proc
        proc.progname = progname
        proc.exit_handler = exit_handler
        logging.notice("ProcessManager: started: {!r} with PID: {}".format(progname, proc.pid))
        return proc

    def coprocess(self, directory=None):
        pid, conn = _fork_coprocess(directory)
        if pid == 0:  # child
            proc = None
            signal.signal(signal.SIGCHLD, signal.SIG_DFL)
            self._procs = {}
            self._zombies = {}
            self.splitter = None
            sys.stdout.flush()
            sys.stderr.flush()
            sys.excepthook = sys.__excepthook__
            _close_stdin()
            _redirect(1, "/tmp/devtest.stdout")
            _redirect(2, "/tmp/devtest.stderr")
            _coprocess_server(conn)
            os._exit(0)
        else:
            proc = CoProcess(pid, conn)
            proc.progname = "CoProcess"
            self._procs[proc.pid] = proc
        logging.notice("ProcessManager: coprocess server with PID: {}".format(pid))
        return proc

    def _sigchild(self, sig, stack):
        # need a real list for loop since dict will be mutated.
        for pid in list(self._procs):
            proc = self._procs[pid]
            if proc.status() == psutil.STATUS_ZOMBIE:
                del self._procs[pid]
                self._zombies[pid] = proc
                es = proc.poll()
                if es < 0:  # signaled
                    es = signal.Signals(-es)
                logging.notice("Exited: {}({}): {}".format(proc.progname, proc.pid, es))

    def run_exit_handlers(self):
        while self._zombies:
            pid, proc = self._zombies.popitem()
            if proc.exit_handler is not None:
                proc.exit_handler(proc)

    def killall(self):
        while self._procs:
            pid, proc = self._procs.popitem()
            proc.interrupt()

    def run_command(self, cmd, timeout=None, input=None, directory=None):
        proc = self.start(cmd, directory=directory)
        return self.run_process(proc, timeout=timeout, input=input)

    def run_process(self, proc, timeout=None, input=None):
        coro = _run_proc(proc, input)
        if timeout:
            coro = timeout_after(float(timeout), coro)
        rv = get_kernel().run(coro)
        if isinstance(rv, Exception):
            raise rv
        return rv

    def call_command(self, cmd, directory=None):
        proc = self.start(cmd, stdin=None, stdout=None, stderr=None,
                          directory=directory)
        coro = _call_proc(proc)
        rv = get_kernel().run(coro)
        if isinstance(rv, Exception):
            raise rv
        return rv


async def _run_proc(proc, input):
    await sleep(0.1)
    try:
        stdout, stderr = await proc.communicate(input)
    except CancelledError as err:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
        raise err
    retcode = proc.poll()
    if retcode:
        return CalledProcessError(retcode, proc.args, output=stdout, stderr=stderr)
    return stdout, stderr


async def _call_proc(proc):
    return await proc._popen.wait()


def call(cmd, timeout=None, directory=None):
    """Run a managed command with stdio inherited from parent.

    Return exit code of subprocess.
    """
    return get_manager().call_command(cmd, timeout=timeout, directory=directory)


_manager = None


def get_manager():
    global _manager
    if _manager is None:
        _manager = ProcessManager()
        atexit.register(_manager.close)
    return _manager


async def start_and_delay(cmd, waittime, **kwargs):
    proc = get_manager().start(cmd, **kwargs)
    await sleep(waittime)
    return proc


def start_process(cmd, delaytime=1.0, **kwargs):
    """Start a process and wait delaytime before returning.

    Gives spawned process a chance to initialize.
    """
    rv = get_kernel().run(start_and_delay(cmd, delaytime, **kwargs))
    get_manager().run_exit_handlers()
    return rv


def run_command(cmd, timeout=None, input=None, directory=None):
    """Run command and collect stdout and stderr.
    """
    return get_manager().run_command(cmd, timeout=timeout, input=input, directory=directory)


def check_output(cmd, shell=False, timeout=None, input=None, cwd=None,
                 encoding=None):
    if shell:
        cmd = ["/bin/sh", "-c"] + ([" ".join(cmd)] if isinstance(cmd, list) else [cmd])
        if encoding is None:  # for backwards compatibility
            encoding = "latin1"
    stdout, stderr = get_manager().run_command(cmd, timeout=timeout, input=input, directory=cwd)
    if encoding is not None:
        return b"".join(stdout).decode(encoding)
    else:
        return b"".join(stdout)


def run_process(proc, timeout=None):
    return get_manager().run_process(proc, timeout=timeout)


def run_coroutine(coro):
    return get_kernel().run(coro)


async def kill_later(proc, waittime):
    await sleep(waittime)
    proc.interrupt()


if __name__ == "__main__":

    import time
    import math

    output, errout = run_command("ls /bin")
    assert output
    print(repr(output))

    try:
        output, errout = run_command("ls /binX")
    except CalledProcessError as cpe:
        print(cpe)
        assert cpe.stderr
        print(repr(cpe.stderr))

    try:
        output, errout = run_command("sleep 10", timeout=5)
    except TaskTimeout as to:
        print(to, "as expected")
    else:
        raise AssertionError("Subprocess did not time out as expected.")

    start_time = time.time()
    proc = start_process(["/bin/sh"], delaytime=3.0)
    end_times = time.time()
    proc.kill()
    print("delaytime", end_times - start_time)
    assert math.isclose(end_times - start_time, 3.0, rel_tol=0.005)

    proc = start_process(["/bin/cat", "-u", "-"])
    proc.write(b"echo me\n")
    resp = proc.read(7)
    print(resp)
    assert resp == b"echo me"
    proc.close()


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
