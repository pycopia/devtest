"""
Controllers and helpers for managing the model.
"""

from functools import wraps
from ast import literal_eval

from devtest.core import constants

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
            q = q.where(models.TestBed.name.contains(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="TestBed not found.")
    def get(testbedname):
        return models.TestBed.select().where(models.TestBed.name == testbedname).get()

    @staticmethod
    def get_equipment(testbedname):
        TE = models.Testequipment
        EQ = models.Equipment
        tb = TestBedController.get(testbedname)
        return list(EQ.select().join(TE).where(TE.testbed == tb))

    @staticmethod
    def create(testbedname, notes=None):
        return models.TestBed.get_or_create(name=testbedname, defaults={"notes": notes})

    @staticmethod
    def update(testbedname, notes=None):
        inst = TestBedController.get(testbedname)
        if inst:
            with models.database.atomic():
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
    def get_all_roles_for_equipment(testbedname, eqname):
        eq = models.Equipment.select().where(models.Equipment.name == eqname).get()
        tb = models.TestBed.select().where(models.TestBed.name == testbedname).get()
        return tb.get_all_roles_for_equipment(eq)

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

    @staticmethod
    def attribute_set(name, attrname, attrvalue):
        inst = TestBedController.get(name)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))

    @staticmethod
    def attribute_del(name, attrname):
        inst = TestBedController.get(name)
        if inst:
            return inst.attribute_del(attrname)

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

    @staticmethod
    def all(like=None):
        q = models.Equipment.select().order_by(models.Equipment.name)
        if like:
            q = q.where(models.Equipment.name.contains(like))
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
    def create(modelname, name, serno=None, accountid=None, userid=None, partof=None, notes=None,
               location=None, attributes=None, manufacturer="Acme Inc."):
        eqmodel = EquipmentModelController.get(modelname, manufacturer)
        if not eqmodel:
            return eqmodel  # NoSuchObject
        if accountid:
            account = AccountIdsController.get(accountid) or None
        else:
            account = None
        if userid:
            user = AccountIdsController.get(userid) or None
        else:
            user = None
        if partof:
            partofeq = EquipmentController.get(partof) or None
        else:
            partofeq = None
        defaults = {
            "serno": serno,
            "notes": notes,
            "account": account,
            "user": user,
            "partof": partofeq,
            "location": location,
            "attributes": attributes,
        }
        return models.Equipment.get_or_create(model=eqmodel, name=name,
                                              defaults=defaults)

    @staticmethod
    def update(modelname, name, serno=None, accountid=None, userid=None, partof=None,
               notes=None, location=None, attributes=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            with models.database.atomic():
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

    @staticmethod
    def attribute_set(name, attrname, attrvalue):
        inst = EquipmentController.get(name)
        if inst:
            return inst.attribute_set(attrname, _eval_value(attrvalue))

    @staticmethod
    def attribute_del(name, attrname):
        inst = EquipmentController.get(name)
        if inst:
            return inst.attribute_del(attrname)

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
    def add_interface(name, iface, modelname=None, ifindex=None,
                      macaddr=None, ipaddr=None, ipaddr6=None, network=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            eq.add_interface(iface, ifindex=ifindex,
                             macaddr=macaddr, ipaddr=ipaddr, ipaddr6=ipaddr6, network=network)
        return eq

    @staticmethod
    def del_interface(name, iface, modelname=None):
        eq = EquipmentController.get(name, modelname)
        if eq:
            eq.del_interface(iface)
        return eq


class EquipmentModelController(Controller):

    @staticmethod
    def all(like=None):
        q = models.EquipmentModel.select().order_by(models.EquipmentModel.name)
        if like:
            q = q.where(models.EquipmentModel.name.contains(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="EquipmentModel not found.")
    def get(modelname, manufacturer="Acme Inc."):
        q = models.EquipmentModel.select().where(models.EquipmentModel.name == modelname,
                                                 models.EquipmentModel.manufacturer == manufacturer)  # noqa
        return q.get()

    @staticmethod
    def create(name, manufacturer="Acme Inc.", note=None, picture=None, specs=None,
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
    def update(name, manufacturer="Acme Inc.", note=None, picture=None,
               specs=None, attributes=None, newmanufacturer=None):
        inst = EquipmentModelController.get(name, manufacturer)
        if inst:
            with models.database.atomic():
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
        return inst.attribute_get(attrname)

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

    @staticmethod
    def attribute_del(modelname, attrname, manufacturer="Acme Inc."):
        inst = EquipmentModelController.get(modelname, manufacturer)
        if inst:
            return inst.attribute_del(attrname)

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


class AccountIdsController(Controller):

    @staticmethod
    def all(like=None):
        q = models.AccountIds.select().order_by(models.AccountIds.identifier)
        if like:
            q = q.where(models.AccountIds.identifier.contains(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="AccountId not found.")
    def get(identifier):
        return models.AccountIds.select().where(models.AccountIds.identifier == identifier).get()

    @staticmethod
    def create(identifier, login=None, password=None, note=None, admin=True):
        defaults = {
            "login": login,
            "password": password,
            "admin": admin,
            "note": note,
        }
        return models.AccountIds.get_or_create(identifier=identifier, defaults=defaults)

    @staticmethod
    def update(identifier, login=None, password=None, note=None, admin=None):

        inst = AccountIdsController.get(identifier)
        if inst:
            with models.database.atomic():
                if login:
                    inst.login = login
                if password:
                    inst.password = password
                if note:
                    inst.note = note
                if admin is not None:
                    inst.admin = bool(admin)
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
            q = q.where(models.Function.name.contains(like))
        return list(q.execute())

    @staticmethod
    @checknotfound(message="Function not found.")
    def get(name):
        return models.Function.select().where(models.Function.name == name).get()

    @staticmethod
    def create(name, description=None, role_implementation=None):
        return models.Function.get_or_create(name=name,
                                             defaults={"description": description,
                                                       "role_implementation": role_implementation})

    @staticmethod
    def update(name, description=None, role_implementation=None):
        inst = FunctionController.get(name)
        if inst:
            with models.database.atomic():
                if description:
                    inst.description = description
                if role_implementation:
                    inst.role_implementation = role_implementation
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
            q = q.where(models.Scenario.name.contains(like))
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
            q = q.where(models.TestSuites.name.contains(like))
        return list(q.execute())

    @staticmethod
    def search(phrase):
        return models.TestSuites.search(phrase)

    @staticmethod
    @checknotfound(message="TestSuite not found.")
    def get(name):
        return models.TestSuites.select().where(models.TestSuites.name == name).get()


class TestCasesController(Controller):

    @staticmethod
    def all(like=None):
        q = models.TestCases.select().order_by(models.TestCases.name)
        if like:
            q = q.where(models.TestCases.name.contains(like))
        return list(q.execute())

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
    def all(resulttype=None, failures=False):
        q = models.TestResults.select().order_by(models.TestResults.starttime)
        if resulttype:
            rt = TestResultsController.RESULT_TYPE_MAP.get(resulttype)
            if rt is None:
                raise ValueError(
                    "Result type one of: {}".format(
                        ", ".join(TestResultsController.RESULT_TYPE_MAP.keys())))
            q = q.where(models.TestResults.resulttype == rt)
        if failures:
            q = q.where(models.TestResults.result != constants.TestResult.PASSED)
        return list(q.execute())

    @staticmethod
    def get_by_id(resultid):
        return models.TestResults.get(id=resultid)

    @staticmethod
    def results_for(testcasename, limit=100):
        tc = TestCasesController.get(testcasename)
        if tc:
            return list(models.TestResults.for_testcase(tc, limit=limit))
        else:
            raise ValueError("TestCase named {} not found.".format(testcasename))

    @staticmethod
    def latest():
        return models.TestResults.get_latest_run()

    @staticmethod
    def subresults(testresult, failures=False):
        q = testresult.subresults.order_by(models.TestResults.starttime)
        if failures:
            q = q.where(models.TestResults.result != constants.TestResult.PASSED)
        return q

def _eval_value(attrvalue):
    try:
        return literal_eval(attrvalue)
    except:
        return attrvalue


def _test(argv):
    models.connect()
    for tb in TestBedController.all():
        print(TestBedController.get_equipment(tb.name))


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
