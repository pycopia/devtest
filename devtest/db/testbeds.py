"""TestBed runtime.

This is the top-level run-time container for Testbed objects.  It also
constructs the run-time wrappers of the equipment it contains.
"""

import sys
from typing import Optional, Callable

import keyring

from devtest import logging
from devtest import importlib
from devtest import debugger
from devtest.db import models
from devtest.qa import signals
from devtest.core.exceptions import ConfigError, TestRunAbort, TestRunnerError


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
        self._supported_roles = None

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
    def localhost(self):
        """An equipment that is always present.
        """
        try:
            return self._eqcache["localhost"]
        except KeyError:
            pass
        EQ = models.Equipment
        eq = EQ.select().where(EQ.name == "localhost").get()
        eq = EquipmentRuntime(eq, "localhost", debug=self._debug)
        self._eqcache["localhost"] = eq
        return eq

    @property
    def SUT(self):
        """Software under test, if testing local software."""
        try:
            return self._eqcache["SUT"]
        except KeyError:
            pass
        sut = SoftwareRuntime(self._testbed.get_SUT(), "SUT")
        self._eqcache["SUT"] = sut
        return sut

    def get_role(self, rolename):
        """Fetch the first equipment in the testbed that provides the role with
        the supplied name.

        Args:
            rolename: name of role, as defined in the database table :py:class:`models.Function`.

        """
        logging.info(f"get_role({rolename}).")
        try:
            return self._eqcache[rolename]
        except KeyError:
            pass
        eq = self._testbed.get_equipment_with_role(rolename)
        eqruntime = EquipmentRuntime(eq, rolename, debug=self._debug)
        self._eqcache[rolename] = eqruntime
        return eqruntime

    def get_all_with_role(self,
                          rolename: str,
                          key: Optional[Callable[..., bool]] = None) -> "EquipmentList":
        """Return an :ref:`EquipmentList` of all equipment with the given role.

        An optional filter function may be given as the *key* parameter.

        Example: ::

            dmms = self.testbed.get_all_with_role("dmm",
                             key=lambda eq: any(name in eq.name for name in ("dmm-1", "dmm-2")))

        That will filter on a substring of the equipment name.

        Args:
            rolename: name of role, as defined in the database table :py:class:`models.Function`.
            key: optional callable to filter returned equipment. It should take a
                 :py:class:`models.Equipment` instance and return a boolean.
        """
        logging.info(f"get_all_with_role({rolename}).")
        if key is not None and not callable(key):
            raise ValueError("filter key must be a callable object.")
        allrolename = rolename + "_all"
        try:
            return self._eqcache[allrolename]
        except KeyError:
            pass
        # If equipment has been already fetched by `get_role` add it here, rather than duplicate it.
        currentset = {eqrt.name for eqrt in self._eqcache.values()}
        eqlist = []
        eqresult = self._testbed.get_all_equipment_with_role(rolename)
        if not eqresult:
            raise ConfigError(f"No equipment with role {rolename} in {self.name}")
        for eq in eqresult:
            if key is not None and not key(eq):
                continue
            if eq.name in currentset:
                existingeq = self._eqcache.get(rolename)
                if existingeq is not None and existingeq.get("role") == rolename:
                    eqlist.append(existingeq)
                else:
                    eqlist.append(EquipmentRuntime(eq, rolename, debug=self._debug))
            else:
                eqlist.append(EquipmentRuntime(eq, rolename, debug=self._debug))
        self._eqcache[allrolename] = eqt = EquipmentList(eqlist)
        return eqt

    def has_role(self, rolename):
        """Check if testbed has a role defined in it.
        """
        return rolename in self.supported_roles

    @property
    def supported_roles(self):
        """Set of roles supported by this testbed.
        """
        if self._supported_roles is None:
            self._supported_roles = self._testbed.get_supported_roles()
        return self._supported_roles

    def claim(self, config):
        if self._testbed.name == "default":
            return
        current_user = self._testbed.attribute_get("current_user")
        if current_user:
            name, timestamp = current_user
            raise TestRunAbort(f"Testbed {self.name} in use by {name} at {timestamp}")
        self._testbed.attribute_set("current_user",
                                    (config.username, config.start_time.strftime("%Y%m%d_%H%M%S")))

    def release(self, config):
        if self._testbed.name == "default":
            return
        current_user, timestamp = self._testbed.attribute_get("current_user")
        if current_user != config.username:
            # Probably a race condition in database update. Deal with it later.
            raise TestRunnerError(
                f"testbed: expected current user of {config.username}, got {current_user}")
        self._testbed.attribute_del("current_user")

    def finalize(self):
        while self._eqcache:
            name, obj = self._eqcache.popitem()
            obj.finalize()

    def clear(self):
        for eq in self._eqcache.values():
            eq.clear()

    # Allow persistent storage of state in the state attribute.
    @property
    def state(self):
        """User-defined state attribute."""
        return self._testbed.attribute_get("state")

    @state.setter
    def state(self, newstate):
        self._testbed.attribute_set("state", newstate)

    @state.deleter
    def state(self):
        self._testbed.attribute_del("state")


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
            d["private_key"] = (bytes(equipmentrow.account.private_key)
                                if equipmentrow.account.private_key else None)
            d["public_key"] = (bytes(equipmentrow.account.public_key)
                               if equipmentrow.account.public_key else b"")
        if equipmentrow.user:  # Alternate user account
            if equipmentrow.user.admin:
                logging.warning("Equipment user marked as admin.")
            d["user"] = equipmentrow.user.login
            d["user_password"] = equipmentrow.user.password
            d["user_private_key"] = (bytes(equipmentrow.user.private_key)
                                     if equipmentrow.user.private_key else None)
            d["user_public_key"] = (bytes(equipmentrow.user.public_key)
                                    if equipmentrow.user.public_key else b"")
        # Be sure to pre-configure this:
        # keyring.set_password("devtest", "ssh_passphrase", "YOUR_PASS_PHRASE")
        d["ssh_passphrase"] = keyring.get_credential("devtest", "ssh_passphrase").password
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
            s.append(f":{port}")
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

    def __contains__(self, key):
        return key in self._attributes

    def get(self, name, default=None):
        return self._attributes.get(name, default)

    def keys(self):
        return self._attributes.keys()

    def values(self):
        return self._attributes.values()

    def items(self):
        return self._attributes.items()

    def pop(self, name, default=None):
        return self._attributes.pop(name, default)

    def get_interface_with_role(self, rolename):
        ifacename = self._attributes.get(rolename)
        if not ifacename:
            raise ConfigError(f"Attempting to get interface with role named {rolename} that "
                              f"isn't configured.")
        return InterfaceRuntime(
            self._equipment.interfaces.select().where(models.Interfaces.name == ifacename).get())

    def get_interface_by_name(self, ifacename):
        return InterfaceRuntime(
            self._equipment.interfaces.select().where(models.Interfaces.name == ifacename).get())

    @property
    def primary_interface(self):
        adminname = self._attributes.get("admin_interface")
        if not adminname:
            return None
        return InterfaceRuntime(
            self._equipment.interfaces.select().where(models.Interfaces.name == adminname).get())

    @property
    def interfaces(self):
        return [InterfaceRuntime(iface) for iface in self._equipment.interfaces]

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
                klass = importlib.get_callable(iobjname)
                self._initializer = klass(self)
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
        """User-defined state attribute."""
        return self._testbed.attribute_get("state")

    @state.setter
    def state(self, newstate):
        self._testbed.attribute_set("state", newstate)

    @state.deleter
    def state(self):
        self._testbed.attribute_del("state")

    @property
    def model(self):
        """The EquipmentModel for this Equipment."""
        return self._equipmentmodel

    def get_components(self, role=None, modelfilter=None):
        """Other equipment defined as components of this one.

        Args:
            role: name of role for component. Same as Function.name in models.
            modelfilter: name of equipment model to select. Default is all components.

        Returns:
            list of EquipmentRuntime for this equipment's sub-components.
        """
        eqlist = []
        for eq in self._equipment.subcomponents:
            if modelfilter:
                if eq.model.name == modelfilter:
                    eqlist.append(EquipmentRuntime(eq, role, self._debug))
            else:
                eqlist.append(EquipmentRuntime(eq, role, self._debug))
        return eqlist

    def service_want(self, name, **kwargs):
        """Request a service from the services modules.

        Return the first non-None response value.
        """
        kwargs.pop("service", None)
        for handler, rv in signals.service_want.send(self, service=name, **kwargs):
            if rv is not None:
                return rv

    def service_dontwant(self, name, **kwargs):
        """Relinquish a service from the services modules."""
        responses = signals.service_dontwant.send(self, service=name, **kwargs)
        for handler, rv in responses:
            if rv is not None:
                return rv


class InterfaceRuntime:
    """Runtime container for interface row objects."""

    def __init__(self, interfacerow):
        self._interface = interfacerow
        attributedict = {}
        attributedict["name"] = interfacerow.name
        # inherit attributes from attached network, if any.
        if (interfacerow.network and interfacerow.network.attributes and
                isinstance(interfacerow.network.attributes, dict)):
            attributedict.update(interfacerow.network.attributes)
        self._attributes = attributedict

    def __getattr__(self, name):
        return getattr(self._interface, name)

    def __getitem__(self, name):
        return self._attributes[name]

    def __setitem__(self, key, value):
        self._attributes[key] = value

    def get(self, name, default=None):
        return self._attributes.get(name, default)

    @property
    def ipv4address(self):
        return self._interface.ipaddr.ip

    @property
    def ipv6address(self):
        return self._interface.ipaddr6.ip

    @property
    def MAC(self):
        return self._interface.macaddr.mac


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


class EquipmentList(tuple):
    """An immutable Sequence of EquipmentRuntime.

    This will perform operations on all contained equipment.

    The contained equipment is always the same type.

    Attributes:
        devices  A list of each device's own controller.
        pdevices  A special attribute that creates a multi-host controller, or raises ConfigError.
    """

    def get(self, name, default=None):
        return [eq.get(name, default) for eq in self]

    def keys(self):
        for eq in self:
            yield from eq.keys()

    def values(self):
        for eq in self:
            yield from eq.values()

    def items(self):
        for eq in self:
            yield from eq.items()

    @property
    def name(self):
        return "+".join(eq.name for eq in self)

    @property
    def devices(self):
        return [eq.device for eq in self]

    @property
    def pdevices(self):
        """Parallel, or concurrent, device controller.

        The controller for this equipment should have a MULTI_CONTROLLER attribute that
        specifies the object that can operate on a collection of equipment similar to that
        controller.
        """
        if hasattr(self, "_multidevice"):
            return self._multidevice
        dev0 = self[0].device
        if hasattr(dev0, "MULTI_CONTROLLER") and dev0.MULTI_CONTROLLER:
            klass = importlib.get_callable(dev0.MULTI_CONTROLLER)
            multidevice = klass.from_equipmentlist(self)
            self._multidevice = multidevice
            return multidevice
        else:
            raise ConfigError(f"No MULTI_CONTROLLER defined for {dev0.name}")

    def finalize(self):
        multidevice = getattr(self, "_multidevice", None)
        if multidevice is not None:
            multidevice.close()
            del self._multidevice
        for eq in self:
            eq.finalize()

    def clear(self):
        multidevice = getattr(self, "_multidevice", None)
        if multidevice is not None:
            multidevice.close()
        for eq in self:
            eq.clear()

    def __del__(self):
        multidevice = getattr(self, "_multidevice", None)
        if multidevice is not None:
            multidevice.close()


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
