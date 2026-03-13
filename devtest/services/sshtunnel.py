"""An SSH tunnel service module.

Provides local, tunneled network connection points for any number of proxy hosts with any number of
tunneled connections.

You can set the attribute "ssh_proxy_config" on the Equipment to something like the following.

.. code-block:: python

    {'proxy_address': ('10.10.14.246', 22),
     'proxy_user': 'testuser',
     'proxy_password': 'xxx',
     }

Otherwise, it will try to figure that out from the equipment model, taking proxy information from
any parent equipment.
"""

import os
import time
import socket
import threading

from devtest import logging
from devtest.core import exceptions
from devtest.io import reactor
from devtest.io import socket as asocket
from devtest.protocols import tlv
from devtest.protocols import ssh

from . import Service

CONTROL_SOCKET = os.path.expandvars(
    f'${{XDG_RUNTIME_DIR}}/devtest_sshtunnel_control_{os.getpid()}.sock')


class SSHTunnelService(Service):

    def __init__(self):
        super().__init__()
        self._server = None

    def _start_server(self):
        if self._server is None:
            self._server = SSHTunnelManagerThread(daemon=False)
            self._server.start()
            time.sleep(0.5)

    def provide_for(self, device, **kwargs):
        self._start_server()
        hostname = device.get("hostname")
        ssh_proxy_config = self.get_config(device, kwargs)
        if not ssh_proxy_config:
            raise exceptions.ConfigNotFoundError(
                f"SSH Tunnel to {hostname} wanted, but has no ssh_proxy_config attribute.")
        with get_client() as c:
            local_port = c.start_tunnel(ssh_proxy_config)
        return ("localhost", local_port)

    def release_for(self, device, **kwargs):
        ssh_proxy_config = self.get_config(device, kwargs)
        if not ssh_proxy_config:
            return
        ssh_proxy_config.setdefault("local_port", kwargs.pop("local_port", 0))
        with get_client() as c:
            c.stop_tunnel(ssh_proxy_config)

    def close(self):
        if self._server is not None:
            try:
                c = get_client()
                c.stop_server()
                c.close()
                del c
            except ConnectionRefusedError:
                pass
            self._server.join()
            self._server = None

    def get_config(self, device, extra: dict) -> dict:
        """Get the configuration of the tunnel.

        Provide:
            - proxy address (ip address, port)
            - proxy user and password
            - destination address (ip address, port)
            - proxy private key

        Obtained from attribute named "ssh_proxy_config" of device.
        May also be set from device information, and updated by the service request.
        """

        ssh_proxy_config = device.get("ssh_proxy_config", {})
        dest_port = extra.pop("port", 22)
        proxy_port = extra.pop("proxy_port", 22)
        ssh_proxy_config.setdefault("dest_address",
                                    (str(device.primary_interface.ipaddr.ip), dest_port))
        if device.parent:
            proxy = device.parent
            proxy_ip = str(proxy.primary_interface.ipaddr.ip)
            ssh_proxy_config["proxy_address"] = (proxy_ip, proxy_port)
            ssh_proxy_config["proxy_user"] = proxy["login"]
            ssh_proxy_config["proxy_password"] = proxy["password"]
            ssh_proxy_config["proxy_private_key"] = proxy["private_key"]
            ssh_proxy_config["proxy_public_key"] = proxy["public_key"]
            ssh_proxy_config["proxy_passphrase"] = proxy["ssh_passphrase"]
        ssh_proxy_config.update(extra)
        return ssh_proxy_config


class SSHTunnelManagerThread(threading.Thread):
    """Runs the asynchronous tunnel manager server in a thread.

    Use the client (which uses the control socket) to send commands.
    """

    def run(self):
        srv = SSHTunnelManagerServer()
        reactor.get_new_kernel().run(srv.run(), shutdown=True)


# tunnel manager client and server objects follow.

# Message types for this application.


class StopServer(tlv.EmptyMessage):
    """Stop the server."""
    TAG = 1000


class StartTunnelMessage(tlv.PickleableMessage):
    TAG = 1001


class StopTunnelMessage(tlv.PickleableMessage):
    TAG = 1002


class StartTunnelResponseMessage(tlv.IntegerMessage):
    TAG = 1003


class SSHTunnelManagerClientMessageFactory(tlv.ClientMessageFactory):

    def stop_server(self):
        return self._request_message_base().append(StopServer.new())

    def start_tunnel(self, config):
        return self._request_message_base().append(StartTunnelMessage.new(config))

    def stop_tunnel(self, config):
        return self._request_message_base().append(StopTunnelMessage.new(config))


class SSHTunnelManagerClient(tlv.ClientBase):

    def __init__(self, clientsock):
        super().__init__(factory=SSHTunnelManagerClientMessageFactory)
        self.connect_socket(clientsock)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.bye()

    def stop_server(self):
        self._socketinterface.send(self._message_factory.stop_server())

    def start_tunnel(self, config):
        resp = self._socketinterface.chat(self._message_factory.start_tunnel(config))

        body = self._message_factory.validate_response(resp)
        local_port = body[0].value
        if local_port == 0:
            raise tlv.ApplicationError("Didn't start tunnel.")
        return local_port

    def stop_tunnel(self, config):
        resp = self._socketinterface.chat(self._message_factory.stop_tunnel(config))
        if not self._message_factory.validate_ok(resp):
            raise tlv.ApplicationError("Didn't stop tunnel.")


def get_client(socketpath=CONTROL_SOCKET):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socketpath)
    client = SSHTunnelManagerClient(sock)
    if not client.hello():
        raise tlv.ApplicationError("Server didn't reply to our hello :-( ")
    return client


# Server side


class SSHTunnelManagerServerMessageFactory(tlv.ServerMessageFactory):

    def do_stop(self, msg):
        plist = msg.value
        if len(plist) < 2:
            return False
        return isinstance(msg.value[2], StopServer)

    def start_tunnel_response(self, clientmessage, port):
        return self._response_message_base(clientmessage).append(
            StartTunnelResponseMessage.new(port))


class SSHTunnelManagerHandlers(tlv.Handlers):
    """Handlers for tunnel manager messages. The "meat" of the application."""

    def __init__(self, factory, logger):
        super().__init__(factory)
        self._logger = logger
        self._tunnels = {}
        self._tg = reactor.TaskGroup()

    async def handle_starttunnelmessage(self, message):
        config = message[1].value
        self._logger.info(f"start tunnel to {config['dest_address']} via {config['proxy_address']}")
        # Example: {'dest_address': ('10.130.10.101', 22),
        #           'proxy_address': ('10.10.14.246', 22), 'proxy_user': 'testuser',
        #           'proxy_private_key': 'xxx',
        #           'proxy_public_key': 'xxx',
        #           'proxy_passphrase': 'xxx',
        #           'proxy_password': 'xxx'}
        # Start new client and the local tunner server
        client = await self._start_client(config)
        tun_server = SSHTunnelServer(client, config["dest_address"], self._logger)
        local_port = await tun_server.start()
        assert local_port != 0
        self._tunnels[local_port] = tun_server
        return self._factory.start_tunnel_response(message, local_port)

    async def handle_stoptunnelmessage(self, message):
        config = message[1].value
        self._logger.info(f"stop tunnel to {config['dest_address']}")
        tun_server = self._tunnels.pop(config["local_port"])
        await tun_server.stop()
        return self._factory.ok_response(message)

    async def _start_client(self, config):
        pkey = config.get("proxy_private_key")
        pubkey = config.get("proxy_public_key")
        client = ssh.AsyncSSHClient()
        await client.connect(config["proxy_address"],
                             config["proxy_user"],
                             password=config.get("proxy_password"),
                             private_key=pkey,
                             public_key=pubkey,
                             passphrase=config.get("ssh_passphrase"))
        return client

    async def stop_all(self):
        while self._tunnels:
            local_port, tun_server = self._tunnels.popitem()
            await tun_server.stop()


class SSHTunnelServer:
    """Manage one local tunnel connection."""

    def __init__(self, sshclient, dest_address, logger):
        self._client = sshclient
        self._dest_address = dest_address
        self._local_port = 0
        self._logger = logger
        self._tg = reactor.TaskGroup()
        self._stop_event = reactor.Event()

    @property
    def local_port(self):
        return self._local_port

    async def start(self):
        # have to block until local port is known.
        start_event = reactor.Event()
        await self._tg.spawn(self.serve, start_event)
        await start_event.wait()
        return self._local_port

    async def stop(self):
        await self._stop_event.set()
        await self._tg.cancel_remaining()
        await self._tg.join()
        await self._client.close()
        self._client = None
        self._local_port = 0

    async def handler(self, csock, addr):
        self._logger.info(f"tunnel client connection from {addr}")
        if isinstance(self._dest_address, tuple):
            chan = await self._client.open_tunnel(self._dest_address, self._local_port)
        elif isinstance(self._dest_address, str):
            chan = await self._client.open_unix_tunnel(self._dest_address, self._local_port)
        else:
            raise ValueError("incorrect destination address type.")
        async with reactor.TaskGroup(wait=any) as tg:
            await tg.spawn(self._copy_to(chan, csock))
            await tg.spawn(self._copy_from(chan, csock))
        await tg.cancel_remaining()
        self._logger.info(f"tunnel client finished from {addr}")
        for ex in tg.exceptions:
            if ex is not None and not isinstance(ex, reactor.TaskCancelled):
                self._logger.exception(ex)
        await chan.close()
        await csock.close()

    async def serve(self, evt):
        sock = asocket.tcp_server_socket("localhost", 0)
        port = sock.getsockname()[1]
        self._logger.info(f"Starting local tunnel server on port {port}")
        serve_task = await self._tg.spawn(asocket.run_server, sock, self.handler)
        self._local_port = port
        await evt.set()
        await self._stop_event.wait()
        await serve_task.cancel()

    async def _copy_to(self, chan, csock):
        while True:
            buf = await csock.recv(4096)
            if not buf:
                break
            await chan.write(buf)

    async def _copy_from(self, chan, csock):
        while True:
            if chan.eof():
                break
            buf = await chan.read(4096)
            await csock.sendall(buf)


class SSHTunnelManagerServer:
    """Server that listens for control messages and manages ssh tunnels.
    """

    def __init__(self, socketpath=CONTROL_SOCKET, factory=SSHTunnelManagerServerMessageFactory):
        self.address = socketpath
        self._logger = logging.get_logger(f"{__name__}.{self.__class__.__name__}")
        self._message_factory = factory()
        self._handlers = SSHTunnelManagerHandlers(self._message_factory, self._logger)
        self._stop_event = reactor.Event()

    async def handler(self, csock, addr):
        netinterface = tlv.AsyncInterface(csock)
        while True:
            try:
                message = await netinterface.receive()
            except EOFError:
                break
            if self._message_factory.is_goodbye(message):
                break
            if self._message_factory.do_stop(message):
                await self._stop_event.set()
                break
            try:
                response = await self.dispatcher(message)
            except Exception as err:
                self._logger.exception(err)
                response = self._message_factory.error_response(message,
                                                                tlv.ApplicationError(str(err)))
            await netinterface.send(response)

    async def dispatcher(self, message):
        try:
            body = self._message_factory.validate(message)
        except tlv.ApplicationProtocolError as exc:
            return self._message_factory.error_response(message, exc)
        return await self._handlers.dispatch(body)

    async def serve(self):
        self._logger.info("Starting server")
        async with reactor.TaskGroup() as tg:
            await tg.spawn(asocket.unix_server, self.address, self.handler)

    async def run(self):
        if os.path.exists(self.address):
            os.unlink(self.address)
        try:
            serv_task = await reactor.spawn(self.serve)
            await self._stop_event.wait()
            self._logger.info("stopping sshtunnel manager server.")
            await self._handlers.stop_all()
            self._handlers = None
            await serv_task.cancel()
            os.unlink(self.address)
        except Exception as err:  # noqa
            self._logger.exception(err)
            self._logger.error("unhandled exception in Server.run")
        self._logger.close()


def initialize(manager):
    srv = SSHTunnelService()
    manager.register(srv, "sshtunnel")


def finalize(manager):
    srv = manager.unregister("sshtunnel")
    srv.close()


if __name__ == "__main__":
    import sys

    control_socket = os.path.expandvars('${XDG_RUNTIME_DIR}/devtest_sshtunnel_control.sock')

    if len(sys.argv) > 1:  # be server if any arg provided
        srv = SSHTunnelManagerServer(socketpath=control_socket)
        reactor.get_kernel(debug=True).run(srv.run())
    else:  # else be client and do a ping
        c = get_client(socketpath=control_socket)
        print(c.ping())
        # c.start_tunnel({})
        c.bye()  # client is now closed

        c = get_client(socketpath=control_socket)
        print(c.ping())
        c.stop_server()  # client is also closed, server has exited
