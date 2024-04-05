# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Services that test cases may need are implemented here.

Services are generall background activities that a test case, or the framework,
my request via the "service_want" signal.

The service gets the equipment runtime object to inspect.

Scans for potential services in this subpackage and initializes
them.
"""

import abc
import pkgutil

from devtest import importlib
from devtest import logging
from devtest.qa import signals
from devtest.core import exceptions

_manager = None


def log_receiver_connected(sig, receiver=None, sender=None, weak=None):
    logging.info("signal.connect: {name!r} receiver={recv!r} sender={sender!r}".format(
        name=sig.name, recv=receiver, sender=sender))


def log_service_want(equipment, service=None, **kwargs):
    logging.info("service wanted by {!r}: {!r} kwargs={!r}".format(equipment.name, service, kwargs))


def log_service_dontwant(equipment, service=None, **kwargs):
    logging.info("service no longer wanted by {!r}: {!r} kwargs={!r}".format(
        equipment.name, service, kwargs))


class Service(abc.ABC):
    """Base class for all services.

    Service class in submodules inherit from this class.
    """

    def provide_for(self, needer, **kwargs):
        """Provide the service for the needer (equipment).
        """
        raise NotImplementedError("provide_for must be implemented")

    def release_for(self, needer, **kwargs):
        """Release the service (service_dontwant signal) when no longer needed.
        """
        raise NotImplementedError("release_for must be implemented")

    def finalize(self):
        pass

    def close(self):
        pass


class ServiceManager:
    """Singleton service manager.
    Provides central dispatcher for service modules provided in this package.

    Responsible for registering, unregistering, and handling the want, and
    dontwant signals.
    """

    def __init__(self):
        self._servicemap = {}
        signals.service_want.connect(self._fulfiller, weak=False)
        signals.service_dontwant.connect(self._releaser, weak=False)

    def close(self):
        self._servicemap = {}
        signals.service_want.disconnect(self._fulfiller)
        signals.service_dontwant.disconnect(self._releaser)

    def register(self, provider, name):
        self._servicemap[name] = provider
        signals.service_provide.send(self, provider=provider, name=name)

    def unregister(self, name):
        return self._servicemap.pop(name, None)

    def fetch(self, name):
        srv = self._servicemap.get(name)
        if srv is None:
            raise exceptions.ConfigError("Service {!r} is not registered.".format(name))
        return srv

    def _fulfiller(self, needer, service=None, **kwargs):
        srv = self._servicemap.get(service)
        if srv is None:
            raise exceptions.ConfigError("{} wants {!r} but is not provided.".format(
                needer, service))
        return srv.provide_for(needer, **kwargs)

    def _releaser(self, needer, service=None, **kwargs):
        srv = self._servicemap.get(service)
        if srv is None:
            raise exceptions.ConfigError(
                "Service {!r} for {} not needed yet does not exist.".format(service, needer))
        return srv.release_for(needer, **kwargs)


def get_manager():
    global _manager
    if _manager is None:
        _manager = ServiceManager()
    return _manager


def _mod_finder():
    for finder, name, ispkg in pkgutil.iter_modules(__path__, prefix=__name__ + "."):
        if not ispkg:
            mod = importlib.import_module(name)
            yield mod


def initialize():
    signals.service_want.connect(log_service_want, weak=False)
    signals.service_dontwant.connect(log_service_dontwant, weak=False)
    signals.service_provide.receiver_connected.connect(log_receiver_connected)
    manager = get_manager()
    for mod in _mod_finder():
        mod.initialize(manager)


def finalize():
    global _manager
    signals.service_want.disconnect(log_service_want)
    signals.service_dontwant.disconnect(log_service_dontwant)
    signals.service_provide.receiver_connected.disconnect(log_receiver_connected)
    manager = get_manager()
    for mod in _mod_finder():
        try:
            mod.finalize(manager)
        # allows all service modules to finalize.
        except Exception as exc:
            logging.exception_error("Exception in finalizer for {}".format(mod), exc)
    manager.close()
    _manager = None


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
