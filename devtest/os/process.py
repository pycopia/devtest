# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Asynchronous process spawner and manager.

Manages all subprocesses and coprocesses.

Also provides the primary object that represents a process, the Process object.
It works with the asynchronous kernel. It also has additional process
informational methods provided by psutil.
"""

from __future__ import generator_stop

import sys
import os
import signal
import atexit
import traceback
import inspect

import psutil

from subprocess import (  # noqa
    CompletedProcess, Popen, SubprocessError, CalledProcessError, PIPE, STDOUT, DEVNULL,
)

from devtest import logging
from devtest.textutils import shparser
from devtest.io import streams
from devtest.io import socket
from devtest.io.reactor import (AWAIT, run_in_thread, get_kernel, sleep, spawn, timeout_after,
                                CancelledError, TaskTimeout)
from devtest.os import procutils
from devtest.os import exitstatus


class ManagerError(Exception):
    pass


class CoProcessError(Exception):
    pass


class ProgramNotFound(ManagerError):
    pass


class APopen:
    '''
    Curio wrapper around the Popen class from the subprocess module. All of the
    methods from subprocess.Popen should be available, but the associated file
    objects for stdin, stdout, stderr have been replaced by async versions.
    Certain blocking operations (e.g., wait() and communicate()) have been
    replaced by async compatible implementations.   Explicit timeouts
    are not available. Use the timeout_after() function for timeouts.
    '''

    def __init__(self, args, **kwargs):
        if 'universal_newlines' in kwargs:
            raise RuntimeError('universal_newlines argument not supported')

        # If stdin has been given and it's set to a curio FileStream object,
        # then we need to flip it to blocking.
        if 'stdin' in kwargs:
            stdin = kwargs['stdin']
            if isinstance(stdin, streams.FileStream):
                # At hell's heart I stab thy coroutine attempting to read from a stream
                # that's been used as a pipe input to a subprocess.  Must set back to
                # blocking or all hell breaks loose in the child.
                if hasattr(os, 'set_blocking'):
                    os.set_blocking(stdin.fileno(), True)

        self._popen = Popen(args, **kwargs)

        if self._popen.stdin:
            self.stdin = streams.FileStream(self._popen.stdin)
        if self._popen.stdout:
            self.stdout = streams.FileStream(self._popen.stdout)
        if self._popen.stderr:
            self.stderr = streams.FileStream(self._popen.stderr)

    def __getattr__(self, name):
        return getattr(self._popen, name)

    async def wait(self):
        retcode = self._popen.poll()
        if retcode is None:
            retcode = await run_in_thread(self._popen.wait)
        return retcode

    async def communicate(self, input=b''):
        '''
        Communicates with a subprocess.  input argument gives data to
        feed to the subprocess stdin stream.  Returns a tuple (stdout, stderr)
        corresponding to the process output.  If cancelled, the resulting
        cancellation exception has stdout_completed and stderr_completed
        attributes attached containing the bytes read so far.
        '''
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
                err.stdout = stdout_task.exception.bytes_read
            else:
                err.stdout = b''

            if stderr_task:
                await stderr_task.cancel()
                err.stderr = stderr_task.exception.bytes_read
            else:
                err.stderr = b''
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self.stdout:
            await self.stdout.close()

        if self.stderr:
            await self.stderr.close()

        if self.stdin:
            await self.stdin.close()

        # Wait for the process to terminate
        await self.wait()

    def __enter__(self):
        return AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return AWAIT(self.__aexit__(*args))


class Process(psutil.Process):

    def interrupt(self):
        logging.debug("Process: interrupt: {}".format(self.pid))
        try:
            self._send_signal(signal.SIGINT)
        except psutil.NoSuchProcess:
            pass


class PipeProcess(Process):
    """Wrapped Popen class that merges async methods and psutil methods.
    """

    def __init__(self, *args, **kwargs):
        self._popen = APopen(*args, **kwargs)
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
        """Return the "universal" ExitStatus object if this process has
        terminated.

        Returns None if process is still running.
        """
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
                err.stdout = stdout_task.exception.bytes_read
            else:
                err.stdout = b''

            if stderr_task:
                await stderr_task.cancel()
                err.stderr = stderr_task.exception.bytes_read
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
    """Main thread representation of a coprocess server.

    Contains both synchronous and asychronous methods.
    """

    def __init__(self, pid, conn):
        self._init(pid, _ignore_nsp=True)
        self._conn = conn

    def start(self, func, *args):
        """Start a method or function in the coprocess.
        """
        return get_kernel().run(self.astart, func, args)

    async def astart(self, func, args):
        msg = (CMD_CALL, func, args)
        try:
            await self._conn.send(msg)
        except CancelledError:
            await self.close()
            raise

    def poll(self):
        """Wait on, and return the status of the coprocess.
        """
        try:
            pid, sts = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return 0
        if pid == self.pid:
            return sts
        else:
            return 0

    def wait(self):
        logging.debug("CoProcess: waiting on: {}".format(self.pid))
        return get_kernel().run(self.a_wait)

    async def a_wait(self):
        resp, result = await self._conn.recv()
        if resp:
            return result
        else:
            if result is not None:
                raise CoProcessError("wait") from result
            else:
                await self._conn.close()

    def close(self):
        get_kernel().run(self.aclose)

    async def aclose(self):
        msg = (CMD_EXIT,)
        await self._conn.send(msg)
        await self._conn.close()

    def ping(self):
        """Verify server is running."""
        return get_kernel().run(self.aping)

    async def aping(self):
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


async def _coprocess_server_coro(conn):
    """This bit runs the coprocess server, waiting for commands.

    The usual command will be the CMD_CALL, sent by the CoProcess start method.

    You can pass any function or method object. But since coroutines are not
    pickle-able, you need a coroutine factory function to invoke one.

    You can also pass code as a string. It will be compiled and executed in the
    coprocess.
    """
    while True:
        msg = await conn.recv()
        cmd = msg[0]
        if cmd == CMD_CALL:
            func, args = msg[1:]
            if isinstance(func, str):
                local_ns = {"args": args}
                global_ns = globals()
                try:
                    code = compile(func, "<coprocess>", "exec")
                    exec(code, global_ns, local_ns)
                except Exception as ex:  # noqa
                    await conn.send((False, ex))
                await conn.send((True, local_ns))
            else:
                try:
                    rv = func(*args)
                    if inspect.iscoroutine(rv):
                        task = await spawn(rv)
                        rv = await task.join()
                except (KeyboardInterrupt, SystemExit) as ex:
                    await conn.send((False, None))
                    await conn.close()
                    break
                except Exception as ex:  # noqa
                    traceback.print_exc(file=sys.stderr)
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
    newfd = os.open(name,
                    os.O_WRONLY | os.O_TRUNC | os.O_CREAT | os.O_NOFOLLOW | os.O_SYNC,
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

    Every other part of the framework should use this, rather than creating a
    subprocess object directly.

    Use the get_manager() factory function to return the singleton.
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

    def start(self,
              commandline,
              stdin=PIPE,
              stdout=PIPE,
              stderr=PIPE,
              directory=None,
              exit_handler=None):
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
        """Start a coprocess server.

        Return a CoProcess object that is the manager for the coprocess.
        Use the `start` method on that to actually run coprocess method.
        """
        pid, conn = _fork_coprocess(directory)
        if pid == 0:  # child
            sys.excepthook = sys.__excepthook__
            proc = None
            signal.signal(signal.SIGCHLD, signal.SIG_DFL)
            self._procs = {}
            self._zombies = {}
            self.splitter = None
            atexit._run_exitfuncs()
            atexit._clear()
            sys.stdout.flush()
            sys.stderr.flush()
            _close_stdin()
            _redirect(1, "/tmp/devtest-coprocess-{}.stdout".format(os.getpid()))
            _redirect(2, "/tmp/devtest-coprocess-{}.stderr".format(os.getpid()))
            try:
                get_kernel().run(_coprocess_server_coro, conn)
            except KeyboardInterrupt:
                pass
            except:  # noqa
                traceback.print_exc(file=sys.stderr)
            os._exit(0)
        else:
            proc = CoProcess(pid, conn)
            proc.progname = "CoProcess"
            self._procs[proc.pid] = proc
        logging.notice("ProcessManager: coprocess server with PID: {}".format(pid))
        return proc

    def _sigchild(self, sig, frame):
        # need a real list for loop since dict will be mutated.
        for pid in list(self._procs):
            proc = self._procs.get(pid)
            if proc is None:
                continue
            try:
                sts = proc.status()
            except psutil.NoSuchProcess:
                self._procs.pop(pid, None)
                # Already waited on somewhere else...
                logging.notice("SIGCHLD no such process: {}({})".format(proc.progname, proc.pid))
                return
            if sts == psutil.STATUS_ZOMBIE:
                self._procs.pop(pid, None)
                self._zombies[pid] = proc
                try:
                    es = proc.poll()
                except ChildProcessError:
                    logging.notice("Already waited: {}({})".format(proc.progname, proc.pid))
                    return
                if es < 0:  # signaled
                    es = signal.Signals(-es)
                logging.notice("Exited: {}({}): {}".format(proc.progname, proc.pid, es))

    def run_exit_handlers(self):
        """Run any exit handler.

        If the start method was supplied an exit_handler, run it if the process
        has exited. Run all available.
        """
        while self._zombies:
            pid, proc = self._zombies.popitem()
            if proc.exit_handler is not None and callable(proc.exit_handler):
                proc.exit_handler(proc)

    def killall(self):
        """Interrupt all managed subprocesses.

        The SIGCHLD handler will handle reaping the exit status.
        """
        while self._procs:
            pid, proc = self._procs.popitem()
            proc.interrupt()

    def run_command(self, cmd, timeout=None, input=None, directory=None):
        """Take a command line argument and communicate with it.

        Return the output, or raise an exception.

        Arguments:
            cmd : str or list
            timeout : optional timeout. Command will be interrupted after this
                      timeout.
            input : str of input to send to command.
            directory : optional directory to change to in subprocess.
        """
        proc = self.start(cmd, directory=directory)
        return self.run_process(proc, timeout=timeout, input=input)

    def run_process(self, proc, timeout=None, input=None):
        """Take a Process instance and communicate with it.
        """
        coro = _run_proc(proc, input)
        if timeout:
            coro = timeout_after(float(timeout), coro)
        output = get_kernel().run(coro)
        if isinstance(output, Exception):
            raise output
        return output

    def call_command(self, cmd, directory=None):
        """Run command, does not collect output.

        Inherits main thread stdio.

        Returns an ExitStatus instance from command.
        """
        proc = self.start(cmd, stdin=None, stdout=None, stderr=None, directory=directory)
        retcode = get_kernel().run(_call_proc(proc))
        return exitstatus.ExitStatus(0, name=proc.progname, returncode=retcode)


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


def call(cmd, directory=None):
    """Run a managed command with stdio inherited from parent.

    Return ExitStatus instance of subprocess.
    """
    return get_manager().call_command(cmd, directory=directory)


_manager = None


def get_manager():
    """Get the process manager singleton.
    """
    global _manager
    if _manager is None:
        _manager = ProcessManager()
        atexit.register(_manager.close)
    return _manager


def close_manager():
    """Close the process manager.
    """
    global _manager
    if _manager is not None:
        _manager.close()
        _manager = None
        atexit.unregister(_manager.close)


async def start_and_delay(cmd, waittime, **kwargs):
    """Start a command, then wait <waittime> seconds before returning.

    Allows command some time to initialize before caller tries to use it.
    """
    proc = get_manager().start(cmd, **kwargs)
    await sleep(waittime)
    return proc


def start_process(cmd, delaytime=1.0, **kwargs):
    """Start a process and wait delaytime before returning.

    Gives spawned process a chance to initialize.
    """
    proc = get_kernel().run(start_and_delay(cmd, delaytime, **kwargs))
    get_manager().run_exit_handlers()
    return proc


def run_command(cmd, timeout=None, input=None, directory=None):
    """Run command and collect stdout and stderr.
    """
    return get_manager().run_command(cmd, timeout=timeout, input=input, directory=directory)


def check_output(cmd, shell=False, timeout=None, input=None, cwd=None, encoding=None):
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
    """Asynchronous method to unconditionally interrupt a process at a later
    time.
    """
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

    print("Coprocess:")
    pm = get_manager()
    coproc = pm.coprocess()
    coproc.start(os.listdir, "/tmp")
    print(coproc.wait())
