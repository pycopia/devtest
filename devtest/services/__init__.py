"""Services that test cases may need are implemented here.

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
    logging.info(
        "signal.connect: {name!r} receiver={recv!r} sender={sender!r}".format(
            name=sig.name, recv=receiver, sender=sender))


def log_service_want(equipment, service=None):
    logging.info("service wanted by {!r}: {!r}".format(equipment.name, service))


def log_service_dontwant(equipment, service=None):
    logging.info("service no longer wanted by {!r}: {!r}".format(equipment.name, service))


class Service(abc.ABC):
    """Base class for all services."""

    def provide_for(self, needer):
        pass

    def release_for(self, needer):
        pass

    def finalize(self):
        pass

    def close(self):
        pass


class ServiceManager:
    """Singleton service manager.
    Provides central dispatcher for service modules provided in this package.
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
            raise exceptions.ConfigError(
                "Service {!r} is not registered.".format(name))
        return srv

    def _fulfiller(self, needer, service=None):
        srv = self._servicemap.get(service)
        if srv is None:
            raise exceptions.ConfigError(
                "{} wants {!r} but is not provided.".format(needer, service))
        return srv.provide_for(needer)

    def _releaser(self, needer, service=None):
        srv = self._servicemap.get(service)
        if srv is None:
            raise exceptions.ConfigError(
                "Service {!r} for {} not needed yet does not exist.".format(service, needer))
        return srv.release_for(needer)


def get_manager():
    global _manager
    if _manager is None:
        _manager = ServiceManager()
    return _manager


def _mod_finder():
    for finder, name, ispkg in pkgutil.iter_modules(__path__,
                                                    prefix=__name__ + "."):
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
