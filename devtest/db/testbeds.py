# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""TestBed runtime.

This is the top-level run-time container for Testbed objects.  It also
constructs the run-time wrappers of the equipment it contains.
"""

import sys

from devtest import logging
from devtest import importlib
from devtest import debugger
from devtest.db import models
from devtest.qa import signals
from devtest.core.exceptions import ConfigError


class TestBedRuntime:
    """Runtime container of a Testbed.

    Contains factory functions for roles.

    Provides a mapping interface to the attributes defined in the database.
    """

    def __init__(self, testbedrow, debug=False):
        self._testbed = testbedrow
        self._debug = debug
        self.name = testbedrow.name
        self._eqcache = {}
        if testbedrow.attributes:
            if isinstance(testbedrow.attributes, dict):
                self._attributes = testbedrow.attributes.copy()
            else:
                self._attributes = {"attributes": testbedrow.attributes}
        else:
            self._attributes = {}

    def __getitem__(self, name):
        return self._attributes[name]

    def __setitem__(self, key, value):
        self._attributes[key] = value

    def get(self, name, default=None):
        return self._attributes.get(name, default)

    def __str__(self):
        s = ["TestBed {} with:".format(self._testbed.name)]
        for teq in self._testbed.testequipment:
            s.append("  {}".format(teq.equipment))
        s.append("  With roles: {}".format(", ".join(self._testbed.get_supported_roles())))
        return "\n".join(s)

    def get_equipment(self, name, role="unspecified"):
        """Get any equipment runtime from the configuration by name."""
        try:
            eqrow = models.Equipment.select().where(models.Equipment.name.contains(name)).get()
        except models.DoesNotExist as err:
            raise ConfigError("Bad equipment name {!r}: {!s}".format(name, err))
        return EquipmentRuntime(eqrow, role, debug=self._debug)

    @property
    def DUT(self):
        """Convenience property for accessing the Equipment defined as the DUT.
        """
        try:
            return self._eqcache["DUT"]
        except KeyError:
            pass
        eq = EquipmentRuntime(self._testbed.get_DUT(), "DUT", debug=self._debug)
        self._eqcache["DUT"] = eq
        return eq

    @property
    def SUT(self):
        try:
            return self._eqcache["SUT"]
        except KeyError:
            pass
        sut = SoftwareRuntime(self._testbed.get_SUT(), "SUT")
        self._eqcache["SUT"] = sut
        return sut

    def get_role(self, rolename):
        """Feth the first equipment in the testbed that provides the role with
        the supplied name.
        """
        try:
            return self._eqcache[rolename]
        except KeyError:
            pass
        eq = self._testbed.get_equipment_with_role(rolename)
        eq = EquipmentRuntime(eq, rolename, debug=self._debug)
        self._eqcache[rolename] = eq
        return eq

    @property
    def supported_roles(self):
        """Roles supported by this testbed.
        """
        return self._testbed.get_supported_roles()

    def finalize(self):
        while self._eqcache:
            name, obj = self._eqcache.popitem()
            obj.finalize()

    # Allow persistent storage of  state in the state attribute.
    @property
    def state(self):
        """User-defined state attribute."""
        return self._testbed.attributes["state"]

    @state.setter
    def state(self, newstate):
        self._testbed.attributes["state"] = str(newstate)

    @state.deleter
    def state(self):
        del self._testbed.attributes["state"]


class EquipmentModelRuntime:
    """Runtime wrapper for equipment models.
    """

    def __init__(self, equipmentmodel):
        d = {}
        d["name"] = equipmentmodel.name
        d["manufacturer"] = equipmentmodel.manufacturer
        if equipmentmodel.attributes and isinstance(equipmentmodel.attributes, dict):
            d.update(equipmentmodel.attributes)
        self._attributes = d

    def __str__(self):
        return "{} {}".format(self._attributes["manufacturer"], self._attributes["name"])

    def __getitem__(self, key):
        return self._attributes[key]

    def __setitem__(self, key, value):
        self._attributes[key] = value

    def get(self, key, default=None):
        return self._attributes.get(key, default)

    @property
    def name(self):
        return self._attributes["name"]


class EquipmentRuntime:
    """Runtime container of information about a device in a testbed.

    Contains the constructor methods for device controller, and others.
    
    Provides a mapping interface to the attributes defined in the database.
    """

    def __init__(self, equipmentrow, rolename, debug=False):
        self.name = equipmentrow.name
        self._equipment = equipmentrow
        self._debug = debug
        self._device = None
        self._parent = None
        self._initializer = None
        self._console = None
        d = {}
        d["hostname"] = equipmentrow.name
        d["serno"] = equipmentrow.serno
        d["modelname"] = equipmentrow.model.name
        d["manufacturer"] = equipmentrow.model.manufacturer
        d["role"] = rolename
        if equipmentrow.attributes and isinstance(equipmentrow.attributes, dict):
            d.update(equipmentrow.attributes)
        if equipmentrow.account:  # Account info takes precedence
            if not equipmentrow.account.admin:
                logging.warning("Equipment account not marked as admin.")
            d["login"] = equipmentrow.account.login
            d["password"] = equipmentrow.account.password
        if equipmentrow.user:  # Alternate user account
            if equipmentrow.user.admin:
                logging.warning("Equipment user marked as admin.")
            d["user"] = equipmentrow.user.login
            d["userpassword"] = equipmentrow.user.password
        self._attributes = d
        self._equipmentmodel = EquipmentModelRuntime(equipmentrow.model)
        signals.device_change.connect(self._on_device_change)

    # handler for device state change. Remove controller since we may need a
    # different controller after the change.
    def _on_device_change(self, controller, state=None):
        if controller is self._device:
            self._device = None
            self._equipment.attributes["state"] = state

    def clear(self):
        """Close any attached controllers.
        """
        if self._device is not None:
            try:
                self._device.close()
            except Exception as err:
                logging.exception_warning("device close: {!r}".format(self._device), err)
            self._device = None
        if self._initializer is not None:
            try:
                self._initializer.close()
            except Exception as err:
                logging.exception_warning("initializer close: {!r}".format(self._initializer), err)
            self._initializer = None
        if self._console is not None:
            try:
                self._console.close()
            except Exception as err:
                logging.exception_warning("console close: {!r}".format(self._initializer), err)
            self._console = None

    def finalize(self):
        self.clear()

    def URL(self, scheme=None, port=None, path=None, with_account=False):
        """Construct a URL that can be used to access the equipment, if the
        equipment supports it.
        """
        attribs = self._attributes
        s = [scheme or attribs.get("serviceprotocol", "http")]
        s.append("://")
        if with_account:
            login = attribs.get("login")
            if login:
                pwd = attribs.get("password")
                if pwd:
                    s.append("%s:%s" % (login, pwd))
                else:
                    s.append(login)
                s.append("@")
        s.append(attribs["hostname"])
        port = attribs.get("serviceport", port)
        if port:
            s.append(":")
            s.append(str(port))
        s.append(path or attribs.get("servicepath", "/"))
        return "".join(s)

    def __str__(self):
        return self._equipment.name

    def __getattr__(self, name):
        return getattr(self._equipment, name)

    def __getitem__(self, name):
        return self._attributes[name]

    def __setitem__(self, key, value):
        self._attributes[key] = value

    def get(self, name, default=None):
        return self._attributes.get(name, default)

    @property
    def primary_interface(self):
        return self._equipment.interfaces[self._attributes.get("admin_interface", "en0")]

    @property
    def parent(self):
        """The device that this device is contained in.

        Returns None if this is not part of another equipment.
        """
        if self._parent is None:
            eq = self._equipment.partof
            if eq is not None:
                self._parent = EquipmentRuntime(eq, self._attributes["role"], debug=self._debug)
        return self._parent

    @property
    def device(self):
        """The controller defined for this equipment."""
        self._initializer = None
        if self._device is None:
            try:
                role = self._attributes["role"]
                self._device = _get_controller(self, role)
            except:  # noqa
                ex, err, tb = sys.exc_info()
                logging.exception_error("Error in device controller construction", err)
                if self._debug:
                    debugger.post_mortem(tb)
                tb = None
                raise ConfigError("controller for {!r} could not be created.".format(role)) from err
        return self._device

    @device.deleter
    def device(self):
        if self._device is not None:
            dev = self._device
            self._device = None
            try:
                dev.close()
            except Exception as ex:
                logging.exception_warning("device close", ex)

    @property
    def initializer(self):
        """The initializing controller defined for this equipment.
        
        Usually a special controller to "bootstrap" a device so that the main
        controller can function.
        """
        if self._initializer is None:
            iobjname = self._attributes.get("initializer",
                                            self.model._attributes.get("initializer"))
            if iobjname is None:
                msg = "'initializer' is not defined in properties."
                logging.error(msg)
                raise ConfigError(msg)
            try:
                self._initializer = _get_controller(self, iobjname)
            except:  # noqa
                ex, err, tb = sys.exc_info()
                msg = "Initializer {!r} could not be created".format(iobjname)
                logging.exception_error(msg, err)
                if self._debug:
                    debugger.post_mortem(tb)
                tb = None
                raise ConfigError(msg) from err
        return self._initializer

    @initializer.deleter
    def initializer(self):
        if self._initializer is not None:
            dev = self._initializer
            self._initializer = None
            try:
                dev.close()
            except Exception as ex:
                logging.exception_warning("initializer close", ex)

    def get_console(self):
        """Fetch any console controller.
        
        A console is another kind of controller that provides console access to
        a device, if it defines one. Usually a serial port.
        """
        if self._console is None:
            console_config = self._attributes.get("console")
            if console_config is None:
                raise ConfigError("Equipment has no console config.")
            signals.service_dontwant.send(self, service="seriallog")
            self._console = _get_console(console_config,
                                         login=self._attributes.get("login"),
                                         password=self._attributes.get("password"))
        return self._console

    @property
    def console(self):
        """Console access to device.

        Often a serial port or port concentrator.
        """
        try:
            return self.get_console()
        except:  # noqa
            ex, err, tb = sys.exc_info()
            msg = "Console could not be created for {!r}".format(self._attributes["hostname"])
            logging.exception_error(msg, err)
            if self._debug:
                debugger.post_mortem(tb)
            tb = None
            raise ConfigError(msg) from err

    @console.deleter
    def console(self):
        if self._console is not None:
            cons = self._console
            self._console = None
            cons.close()
            # Resume serial logging
            signals.service_want.send(self, service="seriallog")

    @property
    def state(self):
        return self._equipment.attributes.get("state")

    @state.setter
    def state(self, newstate):
        self._equipment.attributes["state"] = newstate

    @state.deleter
    def state(self):
        del self._equipment.attributes["state"]

    @property
    def model(self):
        return self._equipmentmodel

    @property
    def components(self):
        """Other equipment defined as components of this one.
        """
        role = self._attributes["role"]
        return [EquipmentRuntime(eq, role) for eq in self._equipment.subcomponents]

    def service_want(self, name, **kwargs):
        """Request a service from the services modules."""
        kwargs.pop("service", None)
        return signals.service_want.send(self, service=name, **kwargs)

    def service_dontwant(self, name, **kwargs):
        """Relinquish a service from the services modules."""
        responses = signals.service_dontwant.send(self, service=name, **kwargs)
        for handler, rv in responses:
            if rv is not None:
                return rv


class SoftwareRuntime:
    """Runtime container of information about software defined in the testbed."""

    def __init__(self, softwarerow, rolename):
        self._software = softwarerow
        self._controller = None
        d = {}
        d["name"] = softwarerow.name
        d["version"] = softwarerow.version
        d["implements"] = softwarerow.implements.name
        d["role"] = rolename
        if softwarerow.attributes and isinstance(softwarerow.attributes, dict):
            d.update(softwarerow.attributes)
        self._attributes = d

    def __str__(self):
        return "{} (version: {})".format(self._software.name, self._software.version)

    def __getattr__(self, name):
        return getattr(self._software, name)

    def __getitem__(self, name):
        return self._attributes[name]

    def __setitem__(self, key, value):
        self._attributes[key] = value

    def get(self, name, default=None):
        return self._attributes.get(name, default)

    @property
    def controller(self):
        if self._controller is None:
            self._controller = _get_software_instance(self)
        return self._controller


def _get_controller(equipmentrt, rolename):
    FM = models.Function
    impl = FM.select(FM.implementation).where(FM.name == rolename).scalar()
    if impl is None:
        raise ConfigError(
            "No implementation for role {!r} found in Function list.".format(rolename))
    klass = importlib.get_callable(impl)
    return klass(equipmentrt)


def _get_console(console_config, login=None, password=None):
    from devtest.device import console
    return console.get_console(console_config, account=login, password=password)


def _get_software_instance(softwarert):
    impl = softwarert.get("implements")
    if not impl:
        raise ConfigError("No implementation defined for software.")
    FM = models.Function
    impl = FM.select(FM.implementation).where(FM.name == impl).scalar()
    obj = importlib.get_callable(impl)
    return obj(softwarert)


def get_testbed(name, storageurl=None, debug=False):
    """Entry point for Testbed, container of the device tree.

    Returns:
        TestBedRuntime initialized from the testbed in the database.
    """
    models.connect(storageurl)
    try:
        testbed = models.TestBed.select().where(models.TestBed.name == name).get()
    except models.DoesNotExist as err:
        raise ConfigError("Bad TestBed name {!r}: {}".format(name, err)) from None
    return TestBedRuntime(testbed, debug=debug)


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else "default"
    testbed = get_testbed(name)
    print(testbed)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
