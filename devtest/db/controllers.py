"""Controllers and helpers for managing the model.
"""

from functools import wraps
from datetime import datetime
from ast import literal_eval

from peewee import JOIN
from devtest.core import constants, exceptions

from . import models


def connect(url=None):
    models.connect(url=url)


class NoSuchObject:

    def __init__(self, message):
        self.message = message

    def __getattr__(self, name):
        return False

    def __str__(self):
        return self.message

    def __bool__(self):
        return False


def checknotfound(message="Not found."):

    def _ifnotfound(f):

        @wraps(f)
        def _f(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except models.DoesNotExist:
                return NoSuchObject(message)

        return _f

    return _ifnotfound


class Controller:
    pass


class TestBedController(Controller):

    @staticmethod
    def all(like=None):
        q = models.TestBed.select().order_by(models.TestBed.name)
        if like:
            q = q.where(models.TestBed.name.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="TestBed not found.")
    def get(testbedname):
        return models.TestBed.select().where(models.TestBed.name == testbedname).get()

    @staticmethod
    def get_equipment(testbedname):
        TE = models._Testequipment
        EQ = models.Equipment
        tb = TestBedController.get(testbedname)
        return list(EQ.select().join(TE).where(TE.testbed == tb))

    @staticmethod
    def create(testbedname, notes=None):
        return models.TestBed.get_or_create(name=testbedname, defaults={"notes": notes})

    @staticmethod
    def update(testbedname, notes=None, newname=None):
        inst = TestBedController.get(testbedname)
        if inst:
            with models.database.atomic():
                if newname:
                    inst.name = newname
                inst.notes = notes
                inst.save()
        return inst

    @staticmethod
    def delete(testbedname):
        with models.database.atomic():
            inst = models.TestBed.select().where(models.TestBed.name == testbedname).get()
            inst.delete_instance()

    @staticmethod
    def add_testequipment(testbedname, equipmentname, rolename):
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        eq = models.Equipment.select().where(models.Equipment.name == equipmentname).get()
        tb.add_testequipment(eq, rolename)

    @staticmethod
    def remove_testequipment(testbedname, equipmentname, rolename):
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        eq = models.Equipment.select().where(models.Equipment.name == equipmentname).get()
        tb.remove_testequipment(eq, rolename)

    @staticmethod
    def get_equipment_with_role(testbedname, rolename):
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        return tb.get_equipment_with_role(rolename)

    @staticmethod
    def get_all_equipment_with_role(testbedname, rolename):
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        return tb.get_all_equipment_with_role(rolename)

    @staticmethod
    def get_all_roles_for_equipment(testbedname, eqname):
        eq = models.Equipment.select().where(models.Equipment.name == eqname).get()
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        return tb.get_all_roles_for_equipment(eq)

    @staticmethod
    def claim(name, username):
        if name == "default":
            return
        tb = TestBedController.get(name)
        if not tb:
            raise ValueError(str(tb))
        current_user_val = tb.attribute_get("current_user")
        if current_user_val:
            current_user, timestamp = current_user_val
            if current_user != username:
                raise exceptions.ConfigError(
                    f"Testbed {tb.name} in use by {current_user} at {timestamp}")
        else:
            tb.attribute_set("current_user", (username, datetime.now().strftime("%Y%m%d_%H%M%S")))

    @staticmethod
    def release(name, username, force=False):
        if name == "default":
            return
        tb = TestBedController.get(name)
        if not tb:
            raise ValueError(str(tb))
        current_user_val = tb.attribute_get("current_user")
        if current_user_val:
            current_user, timestamp = current_user_val
            if current_user == username:
                tb.attribute_del("current_user")
            else:
                if force:
                    tb.attribute_del("current_user")
                else:
                    raise exceptions.ConfigError(
                        f"Can't release: expected current user of {username}, "
                        f"got {current_user}. Use force option to force release.")

    @staticmethod
    def is_claimed(name):
        if name == "default":
            return False
        tb = TestBedController.get(name)
        if not tb:
            raise ValueError(str(tb))
        current_user_val = tb.attribute_get("current_user")
        if current_user_val:
            username, timestamp = current_user_val
            return username, datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
        else:
            return None, None

    @staticmethod
    def clear_old_claim(name):
        if name == "default":
            return False
        tb = TestBedController.get(name)
        if not tb:
            raise ValueError(str(tb))
        current_user_val = tb.attribute_get("current_user")
        if current_user_val:
            username, timestamp = current_user_val
            timestamp = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
            delta = datetime.now() - timestamp
            if delta.days >= 1:
                tb.attribute_del("current_user")

    @staticmethod
    def attribute_list(name):
        inst = TestBedController.get(name)
        if inst and inst.attributes:
            return inst.attributes.items()

    @staticmethod
    def attribute_get(name, attrname):
        inst = TestBedController.get(name)
        if inst:
            return inst.attribute_get(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_set(name, attrname, attrvalue):
        inst = TestBedController.get(name)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_del(name, attrname):
        inst = TestBedController.get(name)
        if inst:
            return inst.attribute_del(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attributes_export(testbedname):
        inst = TestBedController.get(testbedname)
        if inst and inst.attributes:
            return inst.attributes.copy()

    @staticmethod
    def attributes_import(testbedname, attrdict):
        assert isinstance(attrdict, dict), "Attributes need to be a dictionary."
        inst = TestBedController.get(testbedname)
        if inst:
            with models.database.atomic():
                inst.attributes = attrdict
                inst.save()


class EquipmentController(Controller):

    CONNECTION_TYPES = {
        "unknown": constants.ConnectionType.Unknown,
        "serial": constants.ConnectionType.Serial,
        "usb2": constants.ConnectionType.USB2,
        "usb3": constants.ConnectionType.USB3,
        "firewire": constants.ConnectionType.Firewire,
        "lightning": constants.ConnectionType.Lightning,
        "thunderbolt": constants.ConnectionType.Thunderbolt,
        "jtag": constants.ConnectionType.JTAG,
        "bluetooth": constants.ConnectionType.Bluetooth,
        "power": constants.ConnectionType.Power,
        "CAN": constants.ConnectionType.CAN,
    }

    @staticmethod
    def all(like=None):
        q = models.Equipment.select().order_by(models.Equipment.name)
        if like:
            q = q.where(models.Equipment.name.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="Equipment or Model not found.")
    def get(name, modelname=None):
        q = models.Equipment.select().where(models.Equipment.name == name)
        if modelname:
            eqmodel = models.EquipmentModel.select().where(
                models.EquipmentModel.name == modelname).get()
            q = q.where(models.Equipment.model == eqmodel)
        return q.get()

    @staticmethod
    def create(modelname,
               name,
               serno=None,
               accountid=None,
               userid=None,
               partof=None,
               partofeq=None,
               notes=None,
               location=None,
               attributes=None,
               manufacturer="Acme Inc."):
        eqmodel = EquipmentModelController.get(modelname, manufacturer)
        if not eqmodel:
            return eqmodel, False  # NoSuchObject
        if accountid:
            account = AccountIdsController.get(accountid) or None
        else:
            account = None
        if userid:
            user = AccountIdsController.get(userid) or None
        else:
            user = None
        if partof:
            partofeq_ = EquipmentController.get(partof) or None
        else:
            partofeq_ = partofeq
        defaults = {
            "serno": serno,
            "notes": notes,
            "account": account,
            "user": user,
            "partof": partofeq_,
            "location": location,
            "attributes": attributes,
        }
        return models.Equipment.get_or_create(model=eqmodel, name=name, defaults=defaults)

    @staticmethod
    def update(modelname,
               name,
               newname=None,
               newmodel=None,
               newmanufacturer=None,
               serno=None,
               accountid=None,
               userid=None,
               partof=None,
               notes=None,
               location=None,
               attributes=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            if newmodel is not None:
                neweqmodel = EquipmentModelController.get(newmodel, newmanufacturer or
                                                          eq.model.manufacturer)
                if not neweqmodel:
                    return neweqmodel  # NoSuchObject
            else:
                neweqmodel = None
            with models.database.atomic():
                if neweqmodel is not None:
                    eq.model = neweqmodel
                if newname:
                    eq.name = newname
                if serno:
                    eq.serno = serno
                if accountid:
                    eq.account = AccountIdsController.get(accountid) or None
                if userid:
                    eq.user = AccountIdsController.get(userid) or None
                if partof:
                    eq.partof = EquipmentController.get(partof) or None
                if notes:
                    eq.notes = notes
                if location:
                    eq.location = location
                if attributes:
                    eq.attributes = attributes
                eq.save()
        return eq

    @staticmethod
    def delete(modelname, name):
        eq = EquipmentController.get(name, modelname)
        if eq:
            with models.database.atomic():
                eq.delete_instance()

    @staticmethod
    def attribute_list(name, modelname=None):
        inst = EquipmentController.get(name, modelname)
        if inst and inst.attributes:
            return inst.attributes.items()

    @staticmethod
    def attribute_get(name, attrname):
        inst = EquipmentController.get(name)
        if inst:
            return inst.attribute_get(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_set(name, attrname, attrvalue):
        inst = EquipmentController.get(name)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_set_from_file(name, attrname, filename):
        inst = EquipmentController.get(name)
        if inst:
            with open(filename) as fo:
                attrvalue = fo.read()
            return inst.attribute_set(attrname, attrvalue)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_del(name, attrname):
        inst = EquipmentController.get(name)
        if inst:
            return inst.attribute_del(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attributes_export(name, modelname=None):
        inst = EquipmentController.get(name, modelname)
        if inst and inst.attributes:
            return inst.attributes.copy()

    @staticmethod
    def attributes_import(name, attrdict, modelname=None):
        assert isinstance(attrdict, dict), "Attributes need to be a dictionary."
        inst = EquipmentController.get(name, modelname)
        if inst:
            with models.database.atomic():
                inst.attributes = attrdict
                inst.save()

    @staticmethod
    def add_interface(name,
                      iface,
                      modelname=None,
                      ifindex=None,
                      macaddr=None,
                      ipaddr=None,
                      ipaddr6=None,
                      network=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            eq.add_interface(iface,
                             ifindex=ifindex,
                             macaddr=macaddr,
                             ipaddr=ipaddr,
                             ipaddr6=ipaddr6,
                             network=network)
        return eq

    @staticmethod
    def update_interface(name,
                         iface,
                         modelname=None,
                         newname=None,
                         ifindex=None,
                         macaddr=None,
                         ipaddr=None,
                         ipaddr6=None,
                         network=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            eq.update_interface(iface,
                                ifindex=ifindex,
                                newname=newname,
                                macaddr=macaddr,
                                ipaddr=ipaddr,
                                ipaddr6=ipaddr6,
                                network=network)
        return eq

    @staticmethod
    def del_interface(name, iface, modelname=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            eq.del_interface(iface)
        return eq

    @staticmethod
    def add_connection(name, othername, conntype, modelname=None, othermodelname=None):
        conntype = EquipmentController.CONNECTION_TYPES.get(conntype.lower(), conntype)
        eq = EquipmentController.get(name, modelname)
        if eq:
            other = EquipmentController.get(othername, othermodelname)
            eq.add_connection(other, conntype)
        return eq

    @staticmethod
    def del_connection(name, othername, conntype=None, modelname=None, othermodelname=None):
        conntype = EquipmentController.CONNECTION_TYPES.get(conntype)
        eq = EquipmentController.get(name, modelname)
        if eq:
            other = EquipmentController.get(othername, othermodelname)
            eq.remove_connection(other, conntype)
        return eq


class EquipmentModelController(Controller):

    @staticmethod
    def all(like=None):
        q = models.EquipmentModel.select().order_by(models.EquipmentModel.name)
        if like:
            q = q.where(models.EquipmentModel.name.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="EquipmentModel not found.")
    def get(modelname, manufacturer="Acme Inc."):
        q = models.EquipmentModel.select().where(
            models.EquipmentModel.name == modelname,
            models.EquipmentModel.manufacturer == manufacturer)  # noqa
        return q.get()

    @staticmethod
    def create(name,
               manufacturer="Acme Inc.",
               note=None,
               picture=None,
               specs=None,
               attributes=None):
        defaults = {
            "manufacturer": manufacturer,
            "note": note,
            "picture": picture,
            "specs": specs,
            "attributes": attributes,
        }
        return models.EquipmentModel.get_or_create(name=name, defaults=defaults)

    @staticmethod
    def update(name,
               manufacturer="Acme Inc.",
               note=None,
               picture=None,
               specs=None,
               attributes=None,
               newname=None,
               newmanufacturer=None):
        inst = EquipmentModelController.get(name, manufacturer)
        if inst:
            with models.database.atomic():
                if newname:
                    inst.name = newname
                if newmanufacturer:
                    inst.manufacturer = newmanufacturer
                if note:
                    inst.note = note
                if picture:
                    inst.picture = picture
                if specs:
                    inst.specs = specs
                if attributes:
                    inst.attributes = attributes
                inst.save()
        return inst

    @staticmethod
    def delete(modelname, manufacturer="Acme Inc."):
        eqm = EquipmentModelController.get(modelname, manufacturer)
        if eqm:
            with models.database.atomic():
                eqm.delete_instance()

    @staticmethod
    def attribute_get(modelname, attrname, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst:
            return inst.attribute_get(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_list(modelname, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst and inst.attributes:
            return inst.attributes.items()

    @staticmethod
    def attribute_set(modelname, attrname, attrvalue, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_del(modelname, attrname, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst:
            return inst.attribute_del(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attributes_export(modelname, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst and inst.attributes:
            return inst.attributes.copy()

    @staticmethod
    def attributes_import(modelname, attrdict, manufacturer="Acme Inc."):
        assert isinstance(attrdict, dict), "Attributes need to be a dictionary."
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst:
            with models.database.atomic():
                inst.attributes = attrdict
                inst.save()


class NetworksController(Controller):

    NET_TYPE_MAP = {
        None: constants.NetworkType.Unknown,
        'unknown': constants.NetworkType.Unknown,
        'other': constants.NetworkType.Other,
        'ethernet': constants.NetworkType.Ethernet,
        'fibrechannel': constants.NetworkType.FibreChannel,
        'wifi': constants.NetworkType.Wifi,
        'tunnel': constants.NetworkType.Tunnel,
        'vlan': constants.NetworkType.Vlan,
        'usb': constants.NetworkType.USB,
        'aggregate': constants.NetworkType.Aggregate,
        'dummy': constants.NetworkType.Dummy,
        'bluetooth': constants.NetworkType.Bluetooth,  # PAN
    }

    @staticmethod
    def all(like=None):
        q = models.Networks.select().order_by(models.Networks.name)
        if like:
            q = q.where(models.Networks.name.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="Network not found.")
    def get(netname):
        q = models.Networks.select().where(models.Networks.name == netname)
        return q.get()

    @staticmethod
    def create(name, ipnetwork=None, ip6network=None, vlanid=None, layer=3, type=None, notes=None):
        defaults = {
            "ipnetwork": ipnetwork,
            "ip6network": ip6network,
            "vlanid": vlanid,
            "layer": layer,
            "type": NetworksController.NET_TYPE_MAP.get(type),
            "notes": notes,
        }
        return models.Networks.get_or_create(name=name, defaults=defaults)

    @staticmethod
    def update(name,
               ipnetwork=None,
               ip6network=None,
               vlanid=None,
               layer=None,
               type=None,
               notes=None):
        inst = NetworksController.get(name)
        if inst:
            with models.database.atomic():
                if ipnetwork:
                    inst.ipnetwork = ipnetwork
                if ip6network:
                    inst.ip6network = ip6network
                if vlanid is not None:
                    inst.vlanid = vlanid
                if layer is not None:
                    inst.layer = layer
                if type is not None:
                    inst.type = NetworksController.NET_TYPE_MAP.get(type)
                if notes:
                    inst.notes = notes
                inst.save()
        return inst

    @staticmethod
    def delete(name):
        pass
        nw = NetworksController.get(name)
        if nw:
            with models.database.atomic():
                nw.delete_instance()

    @staticmethod
    def interfaces_get(name):
        inst = NetworksController.get(name)
        return inst.interfaces

    @staticmethod
    def attribute_get(netname, attrname):
        inst = NetworksController.get(netname)
        if inst:
            return inst.attribute_get(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_list(netname):
        inst = NetworksController.get(netname)
        if inst and inst.attributes:
            return inst.attributes.items()

    @staticmethod
    def attribute_set(netname, attrname, attrvalue):
        inst = NetworksController.get(netname)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attribute_del(netname, attrname):
        inst = NetworksController.get(netname)
        if inst:
            return inst.attribute_del(attrname)
        else:
            raise ValueError(str(inst))

    @staticmethod
    def attributes_export(netname):
        inst = NetworksController.get(netname)
        if inst and inst.attributes:
            return inst.attributes.copy()

    @staticmethod
    def attributes_import(netname, attrdict):
        assert isinstance(attrdict, dict), "Attributes need to be a dictionary."
        inst = NetworksController.get(netname)
        if inst:
            with models.database.atomic():
                inst.attributes = attrdict
                inst.save()


class AccountIdsController(Controller):

    @staticmethod
    def all(like=None):
        q = models.AccountIds.select().order_by(models.AccountIds.identifier)
        if like:
            q = q.where(models.AccountIds.identifier.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="AccountId not found.")
    def get(identifier):
        return models.AccountIds.select().where(models.AccountIds.identifier == identifier).get()

    @staticmethod
    def create(identifier,
               login=None,
               password=None,
               note=None,
               admin=True,
               private_key=None,
               public_key=None):
        defaults = {
            "login": login,
            "password": password,
            "admin": admin,
            "note": note,
            "private_key": private_key,
            "public_key": public_key,
        }
        return models.AccountIds.get_or_create(identifier=identifier, defaults=defaults)

    @staticmethod
    def update(identifier,
               login=None,
               password=None,
               note=None,
               admin=None,
               private_key=None,
               public_key=None):
        inst = AccountIdsController.get(identifier)
        if inst:
            with models.database.atomic():
                if login:
                    inst.login = login
                if password:
                    inst.password = password
                if password == "None":  # Remove password if setting to None as string.
                    inst.password = None
                if note:
                    inst.note = note
                if admin is not None:
                    inst.admin = bool(admin)
                if private_key is not None:
                    inst.private_key = private_key
                if public_key is not None:
                    inst.public_key = public_key
                inst.save()
        return inst

    @staticmethod
    def delete(identifier):
        inst = AccountIdsController.get(identifier)
        if inst:
            with models.database.atomic():
                inst.delete_instance()


class FunctionController(Controller):

    @staticmethod
    def all(like=None):
        q = models.Function.select().order_by(models.Function.name)
        if like:
            q = q.where(models.Function.name.regexp(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="Function not found.")
    def get(name):
        return models.Function.select().where(models.Function.name == name).get()

    @staticmethod
    def create(name, description=None, implementation=None):
        return models.Function.get_or_create(name=name,
                                             defaults={
                                                 "description": description,
                                                 "implementation": implementation
                                             })

    @staticmethod
    def update(name, description=None, implementation=None):
        inst = FunctionController.get(name)
        if inst:
            with models.database.atomic():
                if description:
                    inst.description = description
                if implementation:
                    inst.implementation = implementation
                inst.save()
        return inst

    @staticmethod
    def delete(name):
        inst = FunctionController.get(name)
        if inst:
            with models.database.atomic():
                inst.delete_instance()


class ScenarioController(Controller):

    @staticmethod
    def all(like=None):
        q = models.Scenario.select().order_by(models.Scenario.name)
        if like:
            q = q.where(models.Scenario.name.regexp(like))
        return list(q.execute())

    @staticmethod
    def search(phrase):
        return models.Scenario.search(phrase)

    @staticmethod
    @checknotfound(message="Scenario not found.")
    def get(name):
        return models.Scenario.select().where(models.Scenario.name == name).get()


class TestSuitesController(Controller):

    @staticmethod
    def all(like=None):
        q = models.TestSuites.select().order_by(models.TestSuites.name)
        if like:
            q = q.where(models.TestSuites.name.regexp(like))
        return list(q.execute())

    @staticmethod
    def search(phrase):
        return models.TestSuites.search(phrase)

    @staticmethod
    @checknotfound(message="TestSuite not found.")
    def get(name):
        return models.TestSuites.select().where(models.TestSuites.name == name).get()


class TestCasesController(Controller):

    STATUSES = {
        None: constants.TestCaseStatus.Unknown,
        "unknown": constants.TestCaseStatus.Unknown,
        "new": constants.TestCaseStatus.New,
        "reviewed": constants.TestCaseStatus.Reviewed,
        "preproduction": constants.TestCaseStatus.Preproduction,
        "production": constants.TestCaseStatus.Production,
        "deprecated": constants.TestCaseStatus.Deprecated,
        "obsolete": constants.TestCaseStatus.Obsolete,
    }

    @staticmethod
    def all(like=None):
        q = models.TestCases.select().order_by(models.TestCases.name)
        if like:
            q = q.where(models.TestCases.name.regexp(like))
        return list(q.execute())

    @staticmethod
    def findall(valid=True, has_implementation=True, **criteria):
        """Find all valid test cases.

        By default, search for those that have implementations. Other criteria (for equality only)
        can be added as additional keyword arguments.
        """
        TC = models.TestCases
        q = TC.select().where(TC.valid == valid,
                              TC.testimplementation.is_null(is_null=not has_implementation),
                              TC.status != constants.TestCaseStatus.Obsolete)
        for name, value in criteria.items():
            col = getattr(TC, name)
            q = q.where(col == value)
        return q.execute()

    @staticmethod
    def invalidate(*names, i_mean_it=False):
        """Mark invalid one or more test cases by name."""
        if not names:
            raise ValueError("must supply at least one name.")
        TC = models.TestCases
        if i_mean_it:
            q = TC.update({TC.valid: False}).where(TC.name.in_(names))
            with models.database.atomic():
                return q.execute()
        else:
            q = TC.select().where((TC.valid == True) & (TC.name.in_(names)))  # noqa
            return q.execute()

    @staticmethod
    def status(*names, status="unknown", i_mean_it=False):
        """Change the status of one or more test cases by name."""
        if not names:
            raise ValueError("must supply at least one name.")
        status = TestCasesController.STATUSES.get(status.lower())
        if status is None:
            raise ValueError('status must be one of '
                             f'{", ".join(str(o) for o in TestCasesController.STATUSES.keys())}')
        TC = models.TestCases
        if i_mean_it:
            q = TC.update({TC.status: status}).where(TC.name.in_(names))
            with models.database.atomic():
                return q.execute()
        else:
            q = TC.select().where(TC.name.in_(names))  # noqa
            return q.execute()

    @staticmethod
    def search(phrase):
        return models.TestCases.search(phrase)

    @staticmethod
    @checknotfound(message="TestCase not found.")
    def get(name):
        return models.TestCases.select().where(models.TestCases.name == name).get()


class TestResultsController(Controller):

    RESULT_TYPE_MAP = {
        'test': constants.TestResultType.Test,
        'suite': constants.TestResultType.TestSuite,
        'summary': constants.TestResultType.TestRunSummary,
    }

    @staticmethod
    def all(resulttype="summary", failures=False, latest=50):
        TRAlias = models.TestResults.alias()
        rt = TestResultsController.RESULT_TYPE_MAP.get(resulttype)
        if rt is None:
            raise ValueError("Result type must be one of: {}".format(", ".join(
                TestResultsController.RESULT_TYPE_MAP.keys())))
        tcq = (TRAlias.select(models.SQL("*"),
                              models.fn.RANK().over(order_by=TRAlias.starttime.desc()).alias(
                                  "rnk")).where((TRAlias.resulttype == rt) &
                                                (TRAlias.valid == True)).alias("tcq"))  # noqa
        if failures:
            tcq = tcq.where(TRAlias.result != constants.TestResult.PASSED)
        q = models.TestResults.select(models.SQL("*")).from_(tcq).where(
            (tcq.c.rnk <= latest)).order_by(tcq.c.starttime)
        return list(q.execute())

    @staticmethod
    def count(testcasename):
        tc = TestCasesController.get(testcasename)
        if tc:
            return models.TestResults.select().where(models.TestResults.testcase == tc).count()

    @staticmethod
    def valid_count(testcasename):
        tc = TestCasesController.get(testcasename)
        if tc:
            return models.TestResults.select().where((models.TestResults.testcase == tc) & (
                models.TestResults.valid == True)).count()  # noqa

    @staticmethod
    def get_by_id(resultid):
        return models.TestResults.get(id=resultid)

    @staticmethod
    def results_for(testcasename, limit=100, offset=0, testbed=None, dutbuild=None):
        tc = TestCasesController.get(testcasename)
        if tc:
            tb = None
            if testbed is not None:
                tb = TestBedController.get(testbed)
                if not tb:
                    raise ValueError("Testbed named {} not found.".format(testbed))
            return list(
                models.TestResults.for_testcase(tc,
                                                limit=limit,
                                                offset=offset,
                                                testbed=tb,
                                                dutbuild=dutbuild))
        else:
            raise ValueError("TestCase named {} not found.".format(testcasename))

    @staticmethod
    def latest_result_for(testcasename):
        tc = TestCasesController.get(testcasename)
        if tc:
            return models.TestResults.get_latest_for_testcase(tc)
        else:
            raise ValueError("TestCase named {} not found.".format(testcasename))

    @staticmethod
    def latest():
        return models.TestResults.get_latest_run()

    @staticmethod
    def runs(limit=20, offset=0):
        return models.TestResults.get_runs(limit=limit, offset=offset)

    @staticmethod
    def recent_for(testcasename, number=10):
        tc = TestCasesController.get(testcasename)
        if tc:
            return list(models.TestResults.get_recent_for_testcase(tc, number=number))
        else:
            raise ValueError("TestCase named {} not found.".format(testcasename))

    @staticmethod
    def subresults(testresult, failures=False):
        q = testresult.subresults.order_by(models.TestResults.starttime)
        if failures:
            q = q.where(models.TestResults.result != constants.TestResult.PASSED)
        return q

    @staticmethod
    def subresults_by_id(root_id):
        testresult = TestResultsController.get_by_id(root_id)
        return TestResultsController.subresults_for_run(testresult)

    @staticmethod
    def latest_run_for_testcase(testcasename):
        res = TestResultsController.latest_result_for(testcasename)
        while res.resulttype != constants.TestResultType.TestRunSummary:
            res = res.parent
        return res

    @staticmethod
    def latest_run_on(testbedname):
        testbed = TestBedController.get(testbedname)
        if not testbed:
            raise ValueError(f"testbed not found: {testbedname}")
        return models.TestResults.get_latest_for_testbed(testbed)

    @staticmethod
    def resultset(rootresult):
        """Full result set from root record.
        """
        return models.TestResults.resultset(rootresult)

    @staticmethod
    def resulttree(rootresult):
        """Partial result set (no data) with testbed and test case names.
        """
        TR = models.TestResults
        TB = models.TestBed
        TC = models.TestCases
        # CTE parts
        TRBase = TR.alias("resulttree")
        RTerm = TR.alias("trr")
        base_case = TRBase.select(
            TRBase.id, TRBase.parent, TRBase.starttime, TRBase.endtime, TRBase.resulttype,
            TRBase.result, TRBase.note, TRBase.diagnostic, TRBase.resultslocation, TRBase.dutbuild,
            TRBase.testbed, TRBase.testcase, TRBase.arguments, TRBase.testversion,
            TRBase.valid).where((TRBase.parent.is_null()) & (TRBase.id == rootresult.id)).cte(
                'base', recursive=True)

        recursive = RTerm.select(RTerm.id, RTerm.parent, RTerm.starttime, RTerm.endtime,
                                 RTerm.resulttype, RTerm.result, RTerm.note, RTerm.diagnostic,
                                 RTerm.resultslocation, RTerm.dutbuild, RTerm.testbed,
                                 RTerm.testcase, RTerm.arguments, RTerm.testversion,
                                 RTerm.valid).join(base_case, on=(RTerm.parent == base_case.c.id))

        cte = base_case.union_all(recursive)
        # Main query
        query = cte.select_from(
            base_case.c.id, base_case.c.parent_id, base_case.c.starttime, base_case.c.endtime,
            base_case.c.resulttype, base_case.c.result, base_case.c.note, base_case.c.diagnostic,
            base_case.c.resultslocation, base_case.c.dutbuild, cte.c.testbed_id,
            TB.name.alias("testbed_name"), cte.c.testcase_id, TC.name.alias("testcase_name"),
            base_case.c.arguments, base_case.c.testversion,
            base_case.c.valid).join(TB, JOIN.LEFT_OUTER, on=(base_case.c.testbed_id == TB.id)).join(
                TC, JOIN.LEFT_OUTER,
                on=(base_case.c.testcase_id == TC.id)).where(cte.c.valid == True).order_by(  # noqa
                    cte.c.starttime)
        return query.execute()


def _eval_value(attrvalue):
    try:
        return literal_eval(attrvalue)
    except:  # noqa
        return attrvalue


def _test(argv):
    for tb in TestBedController.all():
        print(TestBedController.get_equipment(tb.name))


if __name__ == "__main__":
    import sys
    models.connect()
    _test(sys.argv)
