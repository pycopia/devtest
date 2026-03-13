"""SSH2 protocol implementation using libssh2 via ssh2-python3 package.
"""

import os
import stat
import io
import socket
import subprocess
from typing import Dict, Tuple, Optional, Union, Sequence, Generator, cast

from devtest.typing import StringOrBytes, AnyPath

from ssh2.session import Session, ChannelError
from ssh2.channel import Channel
from ssh2.error_codes import LIBSSH2_ERROR_EAGAIN
from ssh2.sftp import (  # noqa: F401
    LIBSSH2_FXF_READ, LIBSSH2_FXF_WRITE, LIBSSH2_FXF_APPEND, LIBSSH2_FXF_CREAT, LIBSSH2_FXF_TRUNC,
    LIBSSH2_FXF_EXCL)
from ssh2.sftp import (  # noqa: F401
    LIBSSH2_SFTP_S_IRUSR, LIBSSH2_SFTP_S_IWUSR, LIBSSH2_SFTP_S_IRGRP, LIBSSH2_SFTP_S_IWGRP,
    LIBSSH2_SFTP_S_IROTH, LIBSSH2_SFTP_S_IWOTH)
from ssh2.sftp_handle import SFTPAttributes
from ssh2.exceptions import Timeout, SocketRecvError, SSH2Error  # noqa

from devtest.os import exitstatus
from devtest.os import filesystem
from devtest.io import reactor
from devtest.io import streams
from devtest.io import socket as asocket

EquipmentList = Sequence

# Needs to be PEM encoded private key with passphrase.
DEFAULT_KEY_FILE = "~/.ssh/id_devtest"

SSH_EXTENDED_DATA_STDERR = 1
SFTP_READABLE = (LIBSSH2_SFTP_S_IRUSR | LIBSSH2_SFTP_S_IRGRP | LIBSSH2_SFTP_S_IROTH)
SFTP_CREATE_MODE = (LIBSSH2_SFTP_S_IRUSR | LIBSSH2_SFTP_S_IWUSR | LIBSSH2_SFTP_S_IRGRP |
                    LIBSSH2_SFTP_S_IWGRP | LIBSSH2_SFTP_S_IROTH)

LIBSSH2_SFTP_OPENFILE = 0
LIBSSH2_SFTP_OPENDIR = 1


def read_private_key(name: Optional[str] = None) -> Optional[bytes]:
    """Read a private key file.

    Also checks for restricted permissions as OpenSSH does.

    Args:
        name: path to private key file.

    Returns:
        The private key if it exists and permissions are correct (readable only by user).
        None if it does not exists.

    Raises:
        RuntimeError if key file exists but has bad permissions.
    """
    basename = os.environ.get("DEVTEST_SSH_KEYFILE", name or DEFAULT_KEY_FILE)
    fname = os.path.expanduser(os.path.expandvars(basename))
    keybytes: Optional[bytes] = None
    if os.path.exists(fname):
        keyfilemode = os.stat(fname).st_mode
        if ((keyfilemode & stat.S_IRUSR) and not (keyfilemode & stat.S_IRGRP) and
                not (keyfilemode & stat.S_IROTH)):
            with open(fname, "rb") as fo:
                keybytes = fo.read()
        else:
            raise RuntimeError(f"Private key file exists with bad mode: "
                               f"{stat.filemode(keyfilemode)}")
    return keybytes


def read_public_key(name: Optional[str] = None, passphrase: Optional[str] = None) -> bytes:
    """Read the public key, which may be a certificate.

    Use the same name as the private key. Will return signed public key (certificate) if that
    exists.

    Generates one from the private key if public part doesn't exist.

    Args:
        name: name of private key file.
        passphrase: optional passphrase if using private key and that key requires a passphrase.
    """
    basename = os.environ.get("DEVTEST_SSH_KEYFILE", name or DEFAULT_KEY_FILE)
    private_name = os.path.expanduser(os.path.expandvars(basename))
    if os.path.exists(fname := private_name + "-cert.pub"):
        return open(fname, "rb").read()
    elif os.path.exists(fname := private_name + ".pub"):
        return open(fname, "rb").read()
    else:
        # Produce public key from private key with ssh-keygen.
        # You should provide a passphrase in this case, if required.
        if not os.path.exists(private_name):
            raise RuntimeError(f"Private key '{private_name}' does not exist.")
        cmd = ['ssh-keygen', '-e', '-m', 'PEM', '-f', private_name]
        passphrase = os.environ.get("TEST_PASSPHRASE", passphrase)
        if passphrase is not None:
            cmd.extend(["-P", str(passphrase)])
        cp = subprocess.run(cmd, stdout=subprocess.PIPE)
        return cp.stdout


class SSHClientBase:
    """An SSH protocol handler.
    """

    def __init__(self):
        self._session = None
        self._sock = None
        self._sftp = None

    @property
    def closed(self):
        return self._session is None


class SSHClient(SSHClientBase):
    """A small and fast SSH client that uses a blocking API."""

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def close(self):
        if self._session is not None:
            # Make sure we don't hold a reference to bad objects in case of errors on closing.
            session = self._session
            sock = self._sock
            self._sftp = None
            self._session = None
            self._sock = None
            session.disconnect()
            sock.close()

    def connect(
            self,
            address: tuple,
            username: str,
            password: Optional[str] = None,
            private_key: Optional[bytes] = None,
            public_key: Optional[bytes] = None,  # may also be certificate
            passphrase: Optional[str] = None,
            use_agent: bool = False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.connect(address)
        session = Session()
        session.handshake(sock)
        if use_agent:
            session.agent_auth(username)
        elif password is not None:
            session.userauth_password(username, password)
        elif private_key is not None and passphrase is not None:
            session.userauth_publickey_frommemory(username,
                                                  private_key,
                                                  passphrase=passphrase,
                                                  publickeyfiledata=public_key)
        else:
            session.disconnect()
            sock.close()
            raise ValueError("An authentication method must be provided.")
        self._session = session
        self._sock = sock

    @property
    def sftp(self):
        """The SFTP channel."""
        if self._sftp is None:
            self._sftp = self._session.sftp_init()
        return self._sftp

    @sftp.deleter
    def sftp(self):
        self._sftp = None

    def run_command(
            self,
            command: str,
            input: Optional[bytes] = None,
            use_pty: bool = False,
            forward_agent: bool = False,
            timeout: Optional[Union[float, int]] = None,
            environment: Optional[dict] = None) -> Tuple[bytes, bytes, exitstatus.ExitStatus]:
        """Run a short-lived command on the remote host.

        Args:
            command: the command line to run on host.
            input: byte string to send to commands stdin.
            use_pty: Allocate a PTY on target, instead of using pipes.
            timeout: Time, in seconds, command may wait to complete. Default is forever.
            environment: Optional set of environment variables to run process with.

        Returns:
            tuple of stdout (bytes), stderr (bytes), and ExitStatus object.
        """
        # Send keep-alive, with response option, every minute.
        # This should, hopefully, keep NAT devices from closing long-lived but quiet connections.
        self._session.keepalive_config(True, 60)
        if timeout is not None:
            original_timeout = self._session.get_timeout()
            self._session.set_timeout(int(timeout * 1000))  # API wants milliseconds.
        else:
            original_timeout = None
        channel = self._session.open_session()
        if isinstance(channel, int):
            raise SSH2Error(f"unhandled ssh2 error: code: {channel}")
        if use_pty:
            channel.pty(term=os.environ.get("TERM", "vt100"))
        if environment:
            for name, value in environment.items():
                channel.setenv(str(name), str(value))
        if forward_agent:
            channel.request_auth_agent()
        channel.execute(command)
        if input:
            channel.write(input)
        buf = io.BytesIO()
        err = io.BytesIO()
        # This will make the libssh2 use an internal poll.
        if not timeout:
            self._session.set_blocking(False)
        try:
            while True:
                try:
                    isize, inp = channel.read(4096)
                    if isize > 0:
                        buf.write(inp)
                    esize, errp = channel.read_stderr(4096)
                    if esize > 0:
                        err.write(errp)
                    if isize <= 0 and esize <= 0:
                        if channel.eof():
                            break
                # Both the timeout feature and keepalive raise this same exception.
                # Try to differentiate the two by checking if timeout was set.
                except Timeout:
                    if channel.eof():
                        break
                    if timeout is not None:
                        raise
        finally:
            self._session.set_blocking(True)

        if original_timeout is not None:
            self._session.set_timeout(original_timeout)
        channel.close()
        es = channel.get_exit_status()
        if original_timeout is not None:
            self._session.set_timeout(original_timeout)
        self._session.keepalive_config(False, 0)
        return buf.getvalue(), err.getvalue(), exitstatus.ExitStatus(None, command, returncode=es)

    def spawn_command(self,
                      command: str,
                      use_pty: bool = False,
                      environment: Optional[dict] = None) -> Channel:
        """Start a command on target host and return immediately.

        Args:
            command: the command line to run on host.
            use_pty: Allocate a PTY on target, instead of using pipes.
            timeout: Time, in seconds, command may wait to complete. Default is forever.
            environment: Optional set of environment variables to run process with.

        Returns:
            ssh2.channel.Channel object.
        """
        channel = self._session.open_session()
        if use_pty:
            channel.pty(term=os.environ.get("TERM", "vt100"))
        if environment:
            for name, value in environment.items():
                channel.setenv(str(name), str(value))
        channel.process_startup("exec", command)
        return channel

    def set_timeout(self, timeout: float) -> float:
        """Set the session socket timeout.

        Args:
            timeout: Time, in seconds, to set the session timeout to.

        Returns:
            Any existing timeout, in seconds.
        """
        original_timeout = self._session.get_timeout()
        self._session.set_timeout(int(timeout * 1000))  # API wants milliseconds.
        return original_timeout / 1000.0

    def listdir(self, path: AnyPath) -> Generator[Tuple[bytes, SFTPAttributes], None, None]:
        """Iterator of entries in path.
        """
        with self.sftp.opendir(str(path)) as sftpdir:
            for size, entry, attrs in sftpdir.readdir():
                if size < 0:
                    continue
                yield entry, attrs

    def read_file(self, path: AnyPath) -> bytes:
        """Read contents of file into bytes buffer.

        Returns contents of file as bytes.
        """
        buf = io.BytesIO()
        handle = self.sftp.open(str(path), LIBSSH2_FXF_READ, SFTP_READABLE)
        try:
            while True:
                size, data = handle.read(4096)
                if size > 0:
                    buf.write(data)
                else:
                    break
        finally:
            handle.close()
        return buf.getvalue()

    def write_file(self,
                   path: AnyPath,
                   data: bytes,
                   mode: int = SFTP_CREATE_MODE,
                   permissions: Optional[int] = None) -> int:
        """Write directly to a file from string.
        """
        handle = self.sftp.open(str(path),
                                LIBSSH2_FXF_WRITE | LIBSSH2_FXF_CREAT | LIBSSH2_FXF_TRUNC, mode)
        try:
            _, written = handle.write(data)
            if permissions is not None:
                permissions = int(permissions)  # asserts it's an integer.
                attrs = handle.fstat()
                attrs.permissions = permissions
                handle.fsetstat(attrs)
        finally:
            handle.close()
        return written

    def unlink(self, path: AnyPath):
        """Unlink (delete) a file.

        Args:
            path: path to file to unlink.
        """
        self.sftp.unlink(str(path))

    def rename(self, source: AnyPath, destination: AnyPath):
        """Rename a file.

        Args:
            source: the path to the source file.
            destination: The path name that the source will be renamed to.
        """
        self.sftp.rename(str(source), str(destination))

    def copy_to(self, source: AnyPath, destination: AnyPath):
        """Copy single file from local source to remote destination.
        """
        fileinfo = os.stat(source)
        chan = self._session.scp_send64(str(destination), fileinfo.st_mode & 0o777,
                                        fileinfo.st_size, fileinfo.st_mtime, fileinfo.st_atime)
        try:
            with open(str(source), "rb") as fo:
                while True:
                    chunk = fo.read(65536)
                    if not chunk:
                        break
                    chan.write(chunk)
            chan.flush()
            chan.send_eof()
            chan.wait_eof()
        finally:
            chan.close()

    def copy_from(self, remote: AnyPath, local: AnyPath):
        """copy single file from remote path to local file.
        """
        chan, fileinfo = self._session.scp_recv2(str(remote))
        size = fileinfo.st_size
        written = 0
        amt = 65536
        try:
            with open(local, "wb") as fo:
                while written < size:
                    readsize, chunk = chan.read(size - written if (size - written) < amt else amt)
                    if readsize > 0:
                        fo.write(chunk)
                    written += readsize
            os.chmod(local, stat.S_IMODE(fileinfo.st_mode))
        finally:
            chan.close()


class SSHHostBase:
    """An object that encapsulates host information and an SSH client protocol handler.
    """

    def __init__(self,
                 hostname: str,
                 username: str,
                 password: Optional[str] = None,
                 private_key: Optional[bytes] = None,
                 public_key: Optional[bytes] = None,
                 passphrase: Optional[str] = None,
                 use_agent: bool = False,
                 port: int = 22):
        self.hostname = hostname
        self.username = username
        self._password = password
        self._private_key = private_key
        self._public_key = public_key
        self._passphrase = passphrase
        self._use_agent = use_agent
        self.port = port
        self._client: SSHClient = cast(SSHClient, None)
        self.initialize()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.hostname!r}, {self.username!r}, ...)"

    def initialize(self):
        pass


class SSHHost(SSHHostBase):
    """An SSH client to particular host.

    May be used to write tools that require SSH access to host.
    Run commands and copy files.
    """

    def initialize(self):
        self._client = SSHClient()

    def __del__(self):
        self.close()

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def _connect(self):
        c = self._client
        if c.closed:
            address = (self.hostname, self.port)
            c.connect(address,
                      self.username,
                      password=self._password,
                      private_key=self._private_key,
                      public_key=self._public_key,
                      passphrase=self._passphrase,
                      use_agent=self._use_agent)

    def run_command(self,
                    command: str,
                    input: Optional[StringOrBytes] = None,
                    use_pty: bool = False,
                    forward_agent: bool = False,
                    environment: Optional[Dict] = None,
                    timeout: Optional[Union[float, int]] = None,
                    encoding: str = "utf8"):
        """Run a short-lived command.

        Returns:
            tuple of stdout, stderr, ExitStatus
        """
        self._connect()
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
        out, err, status = self._client.run_command(command,
                                                    input=inp,
                                                    use_pty=use_pty,
                                                    forward_agent=forward_agent,
                                                    timeout=timeout,
                                                    environment=environment)
        if encoding is None:
            return out, err, status
        else:
            return out.decode(encoding), err.decode(encoding), status

    def listdir(self,
                path: AnyPath,
                encoding: str = "utf8") -> Generator[Tuple[str, filesystem.StatResult], None, None]:
        """Iterator of directory listing.

        Yields:
            tuple of name and stat info.
        """
        self._connect()
        for name, attrs in self._client.listdir(path):
            yield (name.decode(encoding),
                   filesystem.StatResult(_sftp_attribute_to_stat_result(attrs)))

    def read_file(self, path: AnyPath, encoding: str = "utf8"):
        """Read a file content into bytes buffer."""
        self._connect()
        data = self._client.read_file(path)
        return data.decode(encoding)

    def write_file(self,
                   path: AnyPath,
                   data: StringOrBytes,
                   encoding: str = "utf8",
                   permissions: Optional[int] = None):
        """Write string directly into file."""
        self._connect()
        if encoding:
            data = cast(str, data)  # make mypy happy
            data = cast(bytes, data.encode(encoding))
        return self._client.write_file(path, cast(bytes, data), permissions=permissions)

    def copy_to(self, source: os.PathLike, destination: os.PathLike):
        """Copy single file from local source to remote destination.
        """
        self._connect()
        self._client.copy_to(source, destination)

    def copy_from(self, remote: os.PathLike, local: os.PathLike):
        """copy single file from remote path to local file.
        """
        self._connect()
        self._client.copy_from(remote, local)


def _sftp_attribute_to_stat_result(attr: SFTPAttributes) -> os.stat_result:
    # Map SFTP attribute to stat_result:
    #   (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime)
    return os.stat_result(
        (attr.permissions, 0, 0, 1, attr.uid, attr.gid, attr.filesize, attr.atime, attr.mtime, 0))


def run_command(host,
                username: str,
                command: str,
                use_agent: bool = False,
                password: Optional[str] = None,
                private_key: Optional[bytes] = None,
                public_key: Optional[bytes] = None,
                passphrase: Optional[str] = None,
                input: Optional[StringOrBytes] = None,
                timeout: Optional[float] = None,
                use_pty: bool = False,
                forward_agent: bool = False,
                port: int = 22):
    """Run a command on host using SSH.

    Easy way to run a single command on a host.

    Returns:
        stdout, stderr, and ExitStatus
    """

    address = (host, port)
    with SSHClient() as c:
        c.connect(address,
                  username,
                  use_agent=use_agent,
                  password=password,
                  private_key=private_key,
                  public_key=public_key,
                  passphrase=passphrase)
        stdout, stderr, es = c.run_command(command,
                                           input=input,
                                           use_pty=use_pty,
                                           forward_agent=forward_agent,
                                           timeout=timeout)
    return stdout, stderr, es


class AsyncChannel:

    def __init__(self, channel, asock):
        self._channel = channel
        self._fileno = asock.fileno()

    async def close(self):
        if self._channel is not None:
            self._channel.close()
            self._channel = None

    def eof(self):
        return self._channel.eof()

    async def read(self, amt=4096, stream_id=0):
        chan = self._channel
        while True:
            size, buf = chan.read_ex(amt, stream_id)
            if size > 0:
                return buf
            elif size == LIBSSH2_ERROR_EAGAIN:
                await streams.trap_read_wait(self._fileno)
            elif size == 0:
                return b''
            else:
                raise ChannelError(size)  # size is also error code

    async def write(self, data):
        chan = self._channel
        datalen = len(data)
        written = 0
        while written < datalen:
            rc, sent = chan.write(data)
            if rc == LIBSSH2_ERROR_EAGAIN:
                await streams.trap_write_wait(self._fileno)
                continue
            written += sent
            data = data[sent:]
        return written


class AsyncSSHClient(SSHClientBase):
    """A small and fast asynchronous SSH client using non-blocking API."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

    async def close(self):
        if self._session is not None:
            asock = self._sock
            session = self._session
            self._sock = None
            self._session = None
            session.disconnect()
            await asock.close()

    async def connect(self, address, username, password=None, private_key=None, passphrase=None):
        if password is None and passphrase is None:
            raise ValueError("You must supply either password or passphrase to connect.")
        asock = asocket.socket(socket.AF_INET, socket.SOCK_STREAM)
        session = Session()
        await asock.connect(address)
        with asock.blocking() as sock:
            session.handshake(sock)
            if private_key is not None and passphrase is not None:
                session.userauth_publickey_frommemory(username,
                                                      private_key,
                                                      passphrase=passphrase,
                                                      publickeyfiledata=b'')
            elif password is not None:
                session.userauth_password(username, password)
            else:
                session.disconnect()
                await asock.close()
                raise ValueError("need a password or private key file encrypted with password.")
        session.set_blocking(False)
        self._session = session
        self._sock = asock

    async def get_sftp(self):
        """The SFTP channel."""
        sftp = self._session.sftp_init()
        while sftp == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            sftp = self._session.sftp_init()
        return sftp

    async def sftp_open(self, sftp, path):
        """Open SFTP file for reading."""
        handle = sftp.open(str(path), LIBSSH2_FXF_READ, SFTP_READABLE)
        while handle == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            handle = sftp.open(str(path), LIBSSH2_FXF_READ, SFTP_READABLE)
        return handle

    async def sftp_open_write(self, sftp, path, mode):
        """Open SFTP file for writing."""
        handle = sftp.open(str(path), LIBSSH2_FXF_WRITE | LIBSSH2_FXF_CREAT, mode)
        while handle == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            handle = sftp.open(str(path), LIBSSH2_FXF_WRITE | LIBSSH2_FXF_CREAT, mode)
        return handle

    async def open_tunnel(self, address: tuple, local_port: int) -> AsyncChannel:
        remote_host, remote_port = address
        chan = self._session.direct_tcpip_ex(remote_host, remote_port, "127.0.0.1", local_port)
        while chan == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            chan = self._session.direct_tcpip_ex(remote_host, remote_port, "127.0.0.1", local_port)
        assert isinstance(chan, Channel)
        return AsyncChannel(chan, self._sock)

    async def open_unix_tunnel(self, path: str, local_port: int) -> AsyncChannel:
        # We encode message body for generic channel open message.
        msgtype = b"direct-streamlocal@openssh.com"
        host = b"localhost"
        bpath = path.encode("utf8")
        body = len(bpath).to_bytes(4, byteorder="big") + bpath
        body += len(host).to_bytes(4, byteorder="big") + host
        body += local_port.to_bytes(4, byteorder="big")
        # open the generic channel with our carefully crafted message body.
        chan = self._session.open_channel(msgtype, body)
        while chan == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            chan = self._session.open_channel(msgtype, body)
        assert isinstance(chan, Channel)
        return AsyncChannel(chan, self._sock)

    async def read_file(self, path: os.PathLike):
        """Read contents of file into bytes buffer.

        Returns contents of file as bytes.
        """
        buf = io.BytesIO()
        sftp = await self.get_sftp()
        handle = await self.sftp_open(sftp, path)
        try:
            while True:
                size, data = handle.read(4096)
                if size > 0:
                    buf.write(data)
                elif size == LIBSSH2_ERROR_EAGAIN:
                    await streams.trap_read_wait(self._sock)
                else:
                    break
        finally:
            handle.close()
        return buf.getvalue()

    async def write_file(self,
                         path: os.PathLike,
                         data: bytes,
                         mode=SFTP_CREATE_MODE,
                         permissions: int | None = None):
        """Write directly to a file from string.

        Writes all data before ending.
        """
        total = written = 0
        sftp = await self.get_sftp()
        handle = await self.sftp_open_write(sftp, str(path), mode)
        try:
            while True:
                data = data[written:]
                if not data:
                    break
                err, written = handle.write(data)
                total += written
                if err == LIBSSH2_ERROR_EAGAIN:
                    await streams.trap_write_wait(self._sock)

            if permissions is not None:
                permissions = int(permissions)  # asserts it's an integer.
                attrs = handle.fstat()
                while attrs == LIBSSH2_ERROR_EAGAIN:
                    await streams.trap_read_wait(self._sock)
                    attrs = handle.fstat()
                assert isinstance(attrs, SFTPAttributes)
                attrs.permissions = permissions
                await streams.trap_write_wait(self._sock)
                handle.fsetstat(attrs)
        finally:
            handle.close()
        return total

    async def run_command(self, command, input=None, use_pty=False, environment=None):
        """Run a short-lived command on the host.

        It must exit on it's own.
        """
        channel = self._session.open_session()
        while channel == LIBSSH2_ERROR_EAGAIN:
            await streams.trap_read_wait(self._sock)
            channel = self._session.open_session()
        assert isinstance(channel, Channel), "ssh: Didn't get Channel object."
        if use_pty:
            channel.pty(term=os.environ.get("TERM", "vt100"))
        channel.execute(command)
        achan = AsyncChannel(channel, self._sock)
        buf = io.BytesIO()
        err = io.BytesIO()
        if input:
            await achan.write(input)

        # One socket, two streams
        async def read_outputs():
            while True:
                inp = await achan.read(4096)
                if inp:
                    buf.write(inp)
                errinp = await achan.read(4096, stream_id=SSH_EXTENDED_DATA_STDERR)
                if errinp:
                    err.write(errinp)
                if achan.eof():
                    break

        task = await reactor.spawn(read_outputs())
        await task.join()
        await achan.close()
        status = channel.get_exit_status()
        return buf.getvalue(), err.getvalue(), exitstatus.ExitStatus(None,
                                                                     command,
                                                                     returncode=status)


class AsyncSSHHost(SSHHostBase):
    """A host that uses the non-blocking SSH protocol to run commands.
    """

    def initialize(self):
        self._client = AsyncSSHClient()

    async def close(self):
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def connect(self):
        c = self._client
        if c and c.closed:
            address = (self.hostname, self.port)
            await c.connect(address,
                            self.username,
                            password=self._password,
                            private_key=self._private_key,
                            passphrase=self._passphrase)

    async def run_command(self, command, input=None, use_pty=False, environment=None):
        await self.connect()
        return await self._client.run_command(command,
                                              input=input,
                                              use_pty=use_pty,
                                              environment=environment)


class ParallelSSHHost(list):
    """Sequence of AsyncSSHHost that runs methods concurrently.
    """

    def append_host(self, address, user, password=None, private_key=None, passphrase=None, port=22):
        """Append a new AsyncSSHHost client to this list."""
        client = AsyncSSHHost(address,
                              user,
                              password=password,
                              private_key=private_key,
                              passphrase=passphrase,
                              port=port)
        self.append(client)

    @classmethod
    def from_equipmentlist(cls, equipment_list: EquipmentList):  # noqa F821
        newlist = cls()
        for eq in equipment_list:
            newlist.append_host(str(eq.primary_interface.ipaddr.ip),
                                eq.get("login"),
                                password=eq.get("password"),
                                private_key=eq.get("ssh_private_key"),
                                passphrase=eq.get("password"),
                                port=22)
        return newlist

    async def connect(self):
        """Connect all contained clients, concurrently."""
        async with reactor.TaskGroup() as tg:
            for aclient in self:
                await tg.spawn(aclient.connect())

    async def close(self):
        """Close all contained clients, concurrently."""
        async with reactor.TaskGroup() as tg:
            for aclient in self:
                await tg.spawn(aclient.close())

    async def read_file(self, path: os.PathLike):
        """Read contents of file into bytes buffer.

        Returns contents of file as bytes.
        """
        async with reactor.TaskGroup() as tg:
            for aclient in self:
                await tg.spawn(aclient.read_file(path))
        return tg.results

    async def run_command(self, command, input=None, use_pty=False, environment=None):
        """Run command on all contained clients, concurrently."""
        async with reactor.TaskGroup() as tg:
            for aclient in self:
                await tg.spawn(
                    aclient.run_command(command,
                                        input=input,
                                        use_pty=use_pty,
                                        environment=environment))
        return tg.results


async def run_command_async(host,
                            username,
                            command,
                            password=None,
                            private_key=None,
                            passphrase=None,
                            input=None,
                            use_pty=False,
                            environment=None,
                            port=22):
    """Run a command on host using SSH.

    Easy way to run a single command on a host.

    Returns:
        stdout, stderr, and ExitStatus
    """

    private_key = private_key or read_private_key()
    ac = AsyncSSHClient()
    address = (host, port)
    await ac.connect(address,
                     username,
                     password=password,
                     private_key=private_key,
                     passphrase=passphrase)
    stdout, stderr, es = await ac.run_command(command,
                                              input=input,
                                              use_pty=use_pty,
                                              environment=environment)
    await ac.close()
    return stdout, stderr, es


if __name__ == "__main__":
    import sys

    sys.excepthook = sys.__excepthook__  # Remove Ubuntu cruft.
    kern = reactor.get_kernel()

    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEST_HOST", "localhost")
    user = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TEST_USER", os.environ["USER"])
    password = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("TEST_PASSWORD")
    passphrase = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("TEST_PASSPHRASE")

    # two good one bad test case
    TESTS = [("ls /usr/bin", None), ("head -n 2", b"echo me 1\r\necho me 2\r\n"),
             ("ls /binx", None)]
    for cmd, inp in TESTS:
        out, err, status = kern.run(
            run_command(host, user, cmd, input=inp, password=password, passphrase=passphrase))
        print(out)
        print(err)
        print(status)

    client = AsyncSSHHost(host, user, password=password, passphrase=passphrase)
    for cmd, inp in TESTS:
        out, err, status = kern.run(client.run_command(cmd, input=inp))
        print(out)
        print(err)
        print(status)
    # Second use of client should be faster, connection is persistent.
    for cmd, inp in TESTS:
        out, err, status = kern.run(client.run_command(cmd, input=inp))
        print(status)
    kern.run(client.close())
