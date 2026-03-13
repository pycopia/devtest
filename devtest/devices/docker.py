"""Generic interface to Docker deamon as a Controller.

Usable from remote host using Python interface via an SSH tunnel.

For details, see: https://docker-py.readthedocs.io/en/stable/index.html
"""
from __future__ import annotations

import docker
from requests.exceptions import HTTPError  # unfortunate leakage from docker

from devtest import logging
from devtest.qa import signals
from devtest.core import exceptions
from devtest.devices import Controller


class DockerControllerError(exceptions.ControllerError):
    pass


class DockerController(Controller):
    """Control a Docker deamon on the equipment.
    """

    def initialize(self):
        super().initialize()
        eq = self._equipment
        self._docker_socket = eq.get("docker_socket", "/var/run/docker.sock")
        self._docker = None
        self._ipaddr = str(eq.primary_interface.ipaddr.ip)
        self._user = eq["login"]
        self._password = eq["password"]
        self._private_key = eq["private_key"]
        self._public_key = eq["public_key"]
        self._ssh_passphrase = eq["ssh_passphrase"]
        self._local_address = None
        self._connect()
        self._log = logging.get_logger(self._equipment.name)

    def _connect(self):
        if self._docker is None:
            for responder, address in signals.service_want.send(self._equipment,
                                                                service="sshtunnel",
                                                                proxy_address=(self._ipaddr, 22),
                                                                proxy_user=self._user,
                                                                proxy_password=self._password,
                                                                proxy_private_key=self._private_key,
                                                                proxy_public_key=self._public_key,
                                                                ssh_passphrase=self._ssh_passphrase,
                                                                dest_address=self._docker_socket):
                if address is not None:
                    break
            else:
                raise DockerControllerError("local SSH tunnel didn't happen.")

            self._local_address = address
            host, port = address
            self._docker = docker.DockerClient(base_url=f"tcp://{host}:{port}", tls=False)
            self._docker.ping()

    def close(self):
        if self._docker is not None:
            self._docker.close()
            self._docker = None
            signals.service_dontwant.send(self._equipment,
                                          service="sshtunnel",
                                          local_port=self._local_address[1])
            self._local_address = None

    # convenience functions
    def ps(self):
        """Return list of running containers."""
        self._connect()
        return self._docker.containers.list()

    def info(self):
        """Get server information."""
        self._connect()
        return self._docker.info()

    def run(self, image, command=None, **kwargs):
        """Run an image.

        Args:
            image: a Docker Image object.

        Returns:
            A Docker Container object.
        """
        self._connect()
        kwargs["detach"] = True
        return self._docker.containers.run(image, command=command, **kwargs)

    def get(self, name):
        """Get a container by name.

        Returns:
            Container object if running, None if not.
        """
        try:
            container = self._docker.containers.get(name)
        except HTTPError as httperr:
            self._log.warning(str(httperr))
            return None
        else:
            return container

    def remove(self, name):
        """Remove a container by name.
        """
        try:
            container = self._docker.containers.get(name)
        except HTTPError as httperr:
            self._log.warning(str(httperr))
        else:
            if container.status == "running":
                container.kill()
            container.remove()

    def kill(self, name, signal=None):
        """Kill a running container by name.
        """
        try:
            container = self._docker.containers.get(name)
        except HTTPError as httperr:
            self._log.warning(str(httperr))
        else:
            container.kill(signal)

    # API passthrough
    def __getattr__(self, name):
        return getattr(self._docker, name)
