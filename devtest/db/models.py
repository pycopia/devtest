# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Data model for test beds, equipment, and other objects.

These are persistent objects that may model equipment and their
interconnections. They may also have user-specified attributes attached. This
information is made available to test cases using simple attribute accessors.
"""

from datetime import datetime

from pytz import timezone

from peewee import *  # noqa
from .fields import *  # noqa

from .. import json
from ..core import constants
from ..core.exceptions import ModelError


TABLES = ['AccountIds', 'EquipmentModel', 'Equipment',
          'Function', 'Software', 'SoftwareVariant', 'TestBed',
          'Networks', 'Interfaces',
          'TestSuites', 'TestCases', 'Scenario', 'TestResults']

_ASSOC_TABLES = [
    "_SoftwareVariants",
    "_SoftwareRoles",
    "_Testequipment",
    "_Connection",
]

__all__ = TABLES + ['time_now', 'connect']

UTC = timezone('UTC')


def time_now():
    """Return datetime right now, as UTC."""
    return datetime.now(UTC)


database_proxy = Proxy()
database = None


class BaseModel(Model):
    class Meta:
        database = database_proxy


class AccountIds(BaseModel):
    """For lab devices that need authentication for access and control. A good
    place to keep fictitious account passwords. Don't use this for sensitive or
    personal passwords.
    """
    identifier = CharField(max_length=80)
    login = CharField(max_length=80, null=True)
    password = CharField(max_length=80, null=True)
    admin = BooleanField(default=True)
    note = TextField(null=True)

    class Meta:
        table_name = 'account_ids'
        indexes = (
            (("identifier",), True),
        )

    def __str__(self):
        return "AccountId: {}".format(self.identifier)

    @classmethod
    def create_or_get(cls, identifier=None, login=None, password=None):
        try:
            with database.atomic():
                return cls.create(identifier=identifier, login=login,
                                  password=password), True
        except IntegrityError:
            return cls.get(cls.identifier == identifier), False


class EquipmentModel(BaseModel):
    """A model, or type of, equipment. This includes components of other
    equipment.
    """
    name = CharField(max_length=255)
    manufacturer = CharField(max_length=255)
    note = TextField(null=True)
    picture = BlobField(null=True)
    specs = CharField(max_length=255, null=True)  # URL
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)

    class Meta:
        table_name = 'equipment_model'
        indexes = (
            (("name", "manufacturer"), True),
        )

    def __str__(self):
        return "{} {}".format(self.manufacturer, self.name)

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)

    @classmethod
    def create_or_get(cls, name=None, manufacturer=None, attributes=None):
        try:
            with database.atomic():
                return cls.create(name=name, manufacturer=manufacturer,
                                  attributes=attributes), True
        except IntegrityError:
            return (cls.get(cls.name == name,
                            cls.manufacturer == manufacturer), False)


class Equipment(BaseModel):
    """Various equipment. This can be devices under test, support devices,
    infrastructure devices, etc. May also be a component of another Equipment.
    These are also "instances" of EquipmentModel.
    """

    name = CharField(max_length=255, unique=True)
    serno = CharField(max_length=255, null=True)
    model = ForeignKeyField(column_name='model_id',
                            model=EquipmentModel, field='id',
                            backref='equipment')
    account = ForeignKeyField(column_name='account_id', null=True,
                              model=AccountIds, field='id')
    user = ForeignKeyField(column_name='user_id', null=True,
                           model=AccountIds, field='id',
                           backref='user_equipment_set',
                           on_update="CASCADE", on_delete="SET NULL")
    partof = ForeignKeyField(column_name='partof_id', null=True,
                             model='self', field='id',
                             backref='subcomponents',
                             on_update="CASCADE", on_delete="SET NULL")
    location = TextField(null=True)
    notes = TextField(null=True)
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)
    active = BooleanField(default=True)

    class Meta:
        table_name = 'equipment'

    def __str__(self):
        return self.name

    @classmethod
    def create_or_get(cls, name=None, serno=None, model=None, account=None,
                      attributes=None):
        try:
            with database.atomic():
                return cls.create(name=name, serno=serno, model=model, account=account,
                                  attributes=attributes), True
        except IntegrityError:
            return cls.get(cls.name == name), False

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)

    def add_interface(self, name, ifindex=None,
                      macaddr=None, ipaddr=None, ipaddr6=None, network=None):
        if network is not None and isinstance(network, str):
            network = Networks.select().where(Networks.name == network).get()
        with database.atomic():
            Interfaces.create(name=name, equipment=self, ifindex=ifindex,
                              macaddr=macaddr, ipaddr=ipaddr, ipaddr6=ipaddr6,
                              network=network)

    def attach_interface(self, **selectkw):
        """Attach an existing interface entry that is currently detached."""
        q = Interfaces.select()
        for attrname, value in list(selectkw.items()):
            q = q.where(getattr(Interfaces, attrname) == value)
        intf = q.get()
        if intf.equipment is not None:
            raise ModelError(
                "Interface already attached to {!r}".format(intf.equipment))
        with database.atomic():
            intf.equipment = self

    def del_interface(self, name):
        with database.atomic():
            intf = self.interfaces.where(Interfaces.name == name).get()
            intf.delete_instance()

    # Device connection management
    def add_connection(self, other, connection_type):
        if isinstance(other, str):
            other = Equipment.select().where(Equipment.name == other).get()
        with database.atomic():
            _Connection.create(source=self, destination=other, type=connection_type)

    def remove_connection(self, other, connection_type=None):
        with database.atomic():
            q = _Connection.select().where((_Connection.source == self) &
                                           (_Connection.destination == other))
            if connection_type is not None:
                q = q.where(_Connection.type == connection_type)
            conn = q.get()
            conn.delete_instance()

    def get_connected(self, connection_type):
        """Return equipment on other end of a connection."""
        conn = self.connections.filter(type=connection_type).get()
        return conn.destination

    def set_connection_state(self, connection_type, state):
        conn = self.connections.filter(type=connection_type).get()
        with database.atomic():
            conn.state = int(state)

    def get_connection_state(self, connection_type):
        conn = self.connections.filter(type=connection_type).get()
        return conn.state


class Function(BaseModel):
    """The function, or purpose of a device or software. This is a generic
    name, such as "webserver", "camera", "jtag", "accesspoint", or "router".

    This name maps to controller objects with abstract interfaces for this
    function.
    """
    name = CharField(max_length=80, unique=True)
    description = TextField(null=True)
    implementation = CharField(max_length=255, null=True)

    class Meta:
        table_name = 'function'

    def __str__(self):
        return "Function: {}".format(self.name)

    @classmethod
    def create_or_get(cls, name=None, description=None, implementation=None):
        try:
            with database.atomic():
                return cls.create(name=name, description=description,
                                  implementation=implementation), True
        except IntegrityError:
            return cls.get(cls.name == name), False

    @classmethod
    def get_by_name(cls, name):
        try:
            func = cls.select().where(cls.name == str(name)).get()
        except DoesNotExist:
            raise ModelError("No Function {!r} defined.".format(name))
        return func

    @classmethod
    def get_role_names(cls):
        return [t[0] for t in cls.select(cls.name).tuples()]

    @classmethod
    def get_implementation(cls, name):
        return cls.select(cls.implementation).where(cls.name == name).scalar()


class Software(BaseModel):
    """A specific software, by name, that implements a particular function.
    """
    name = CharField(max_length=255, unique=True)
    version = CharField(max_length=255, null=True)
    implements = ForeignKeyField(column_name='category_id',
                                 model=Function, field='id',
                                 backref="implementations")
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)

    class Meta:
        table_name = 'software'

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)


class SoftwareVariant(BaseModel):
    branch = CharField(max_length=80)
    target = CharField(max_length=80)
    build = CharField(max_length=80)

    class Meta:
        table_name = 'software_variant'

    def __str__(self):
        return "{}-{}-{}".format(self.branch, self.target, self.build)


class _SoftwareVariants(BaseModel):
    software = ForeignKeyField(column_name='software_id',
                               model=Software, field='id',
                               backref="variants")
    softwarevariant = ForeignKeyField(column_name='softwarevariant_id',
                                      model=SoftwareVariant, field='id')

    class Meta:
        table_name = 'software_variants'
        primary_key = CompositeKey('software', 'softwarevariant')


class TestBed(BaseModel):
    """An TestBed is a collection of equipment that is associated in some way.
    Equipment can be assigned roles. These roles are selected in a test
    scenario.  A testbed should contain all the devices necessary to perform
    the test.  You may also attach arbitrary attributes to it for use by test
    cases.
    """
    name = CharField(max_length=255, unique=True)
    notes = TextField(null=True)
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)

    class Meta:
        table_name = 'testbeds'

    def __str__(self):
        return self.name

    @classmethod
    def create_or_get(cls, name=None, notes=None, attributes=None):
        try:
            with database.atomic():
                return cls.create(name=name, notes=notes,
                                  attributes=attributes), True
        except IntegrityError:
            return cls.get(cls.name == name), False

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)

    def get_supported_roles(self):
        roles = set()
        for te in _Testequipment.select().where(_Testequipment.testbed == self):
            if te.function:
                roles.add(te.function.name)
        return roles

    @classmethod
    def get_list(cls):
        """Return list of defined TestBed names."""
        return [t[0] for t in cls.select(cls.name).tuples()]

    def get_DUT(self):
        return self.get_equipment_with_role("DUT")

    def get_SUT(self):
        sut = self.get_software_with_role("SUT")
        if sut:
            return sut[0]
        else:
            raise ModelError("SUT is not defined in testbed '{}'.".format(self.name))

    def get_software_with_role(self, rolename):
        q = (Software.select().join(_SoftwareRoles).join(Function)
             .where(Function.name == rolename)
             .switch(_SoftwareRoles).where(_SoftwareRoles.testbed == self))
        return q.peek(n=100)

    def add_software_role(self, software, rolename):
        func = Function.select().where(Function.name == rolename).get()
        with database.atomic():
            _SoftwareRoles.create(testbed=self, software=software, function=func)

    def add_testequipment(self, eq, rolename):
        func = Function.select().where(Function.name == rolename).get()
        with database.atomic():
            te, created = _Testequipment.create_or_get(testbed=self,
                                                       equipment=eq,
                                                       function=func)

    def remove_testequipment(self, eq, rolename):
        func = Function.select().where(Function.name == rolename).get()
        with database.atomic():
            te = _Testequipment.select().where(_Testequipment.testbed == self,
                                               _Testequipment.function == func,
                                               _Testequipment.equipment == eq).get()
            te.delete_instance()

    def get_equipment_with_role(self, rolename):
        res = self.get_all_equipment_with_role(rolename)
        if res:
            return res[0]
        else:
            raise ModelError("No equipment with role {!r} defined.".format(rolename))

    def get_all_equipment_with_role(self, rolename):
        q = (Equipment.select().join(_Testequipment)
             .join(Function).where(Function.name == rolename)
             .switch(_Testequipment).where(_Testequipment.testbed == self))
        return q.peek(n=100)

    def get_all_roles_for_equipment(self, eq):
        q = (Function.select().join(_Testequipment)
             .where((_Testequipment.testbed == self) & (_Testequipment.equipment == eq)))
        return q.peek(n=100)


# Maps a testbed to equipment.
class _Testequipment(BaseModel):
    testbed = ForeignKeyField(column_name='testbed_id',
                              model=TestBed, field='id',
                              backref="testequipment",
                              on_update="CASCADE", on_delete="CASCADE")
    equipment = ForeignKeyField(column_name='equipment_id',
                                model=Equipment, field='id',
                                backref="testequipment",
                                on_update="CASCADE", on_delete="CASCADE")
    function = ForeignKeyField(column_name='function_id', null=True,
                               model=Function, field='id',
                               on_update="CASCADE", on_delete="CASCADE")

    class Meta:
        table_name = 'testequipment'
        indexes = (
            (("testbed", "equipment", "function"), True),
        )

    def __str__(self):
        return "{} in TestBed {} as {}".format(self.equipment.name,
                                               self.testbed.name,
                                               self.function.name)

    @classmethod
    def create_or_get(cls, testbed=None, equipment=None, function=None):
        try:
            with database.atomic():
                return cls.create(testbed=testbed, equipment=equipment,
                                  function=function), True
        except IntegrityError:
            return (cls.get(cls.testbed == testbed, cls.equipment == equipment,
                            cls.function == function), False)


class _SoftwareRoles(BaseModel):
    testbed = ForeignKeyField(column_name='testbed_id',
                              model=TestBed, field='id',
                              on_update="CASCADE", on_delete="CASCADE")
    software = ForeignKeyField(column_name='software_id',
                               model=Software, field='id',
                               on_update="CASCADE", on_delete="CASCADE")
    function = ForeignKeyField(column_name='function_id',
                               model=Function, field='id',
                               on_update="CASCADE", on_delete="CASCADE")

    class Meta:
        table_name = 'software_roles'
        primary_key = CompositeKey('testbed', 'software', 'function')


# Model the connections of accessories and non-networked wired or wireless
# connections. These are point-to-point connections with no configurable
# addressing.
class _Connection(BaseModel):
    source = ForeignKeyField(column_name='source_id',
                             model=Equipment, field='id',
                             backref="connections",
                             on_delete="CASCADE")
    destination = ForeignKeyField(column_name='destination_id',
                                  model=Equipment, field='id',
                                  backref="connected",
                                  on_delete="CASCADE")
    type = EnumField(constants.ConnectionType,
                     default=constants.ConnectionType.Unknown)
    state = IntegerField(null=True)  # User defined state

    class Meta:
        table_name = 'connections'

    def __str__(self):
        return "{} <-<{}>-> {}".format(self.source.name, self.type.name,
                                       self.destination.name)


class Networks(BaseModel):
    """Represents multiple-access networks. May represent different layers
    of the OSI model. Each layer is linked using the "lower" column.
    """
    name = CharField(max_length=64)
    ipnetwork = CIDRField(null=True)
    ip6network = CIDRField(null=True)
    vlanid = IntegerField(null=True)
    layer = IntegerField(default=3)
    lower = ForeignKeyField(column_name='lower_id', null=True,
                            model='self', field='id',
                            backref="upper")
    type = EnumField(constants.NetworkType,
                     default=constants.NetworkType.Unknown)
    notes = TextField(null=True)
    # User defined attributes.
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)

    class Meta:
        table_name = 'networks'
        constraints = [Check('vlanid >= 0 AND vlanid < 4096')]

    def __str__(self):
        if self.layer == 2 and self.vlanid is not None:
            return "{} <{}>".format(self.name, self.vlanid)
        elif self.layer == 3 and self.ipnetwork is not None:
            return "{} ({})".format(self.name, self.ipnetwork)
        else:
            return "{}[{}]".format(self.name, self.layer)

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)


class Interfaces(BaseModel):
    """Network interfaces bind an Equipment to a Network and have attributes
    such as addresses. Allows for virtual interfaces parent column to map the
    physical interface to the virtual one.
    """
    name = CharField(max_length=64)
    alias = CharField(max_length=64, null=True)
    status = IntegerField(null=True)
    ipaddr = IPv4Field(null=True)  # inet
    ipaddr6 = IPv6Field(null=True)  # inet
    macaddr = MACField(null=True)  # macaddr
    vlan = IntegerField(null=True, default=0)
    parent = ForeignKeyField(column_name='parent_id', null=True,
                             model='self', field='id',
                             backref="subinterface",
                             on_update="CASCADE",
                             on_delete="SET NULL")
    equipment = ForeignKeyField(column_name='equipment_id', null=True,
                                model=Equipment, field='id',
                                backref="interfaces",
                                on_delete="CASCADE")
    network = ForeignKeyField(column_name='network_id', null=True,
                              model=Networks, field='id',
                              on_update="CASCADE",
                              on_delete="SET NULL")

    class Meta:
        table_name = 'interfaces'
        constraints = [Check('vlan >= 0 AND vlan < 4096')]

    def __str__(self):
        return "{} (ip:{}, mac:{})".format(self.name, self.ipaddr, self.macaddr)


class TestSuites(BaseModel):
    name = CharField(max_length=255, unique=True)
    purpose = TextField(null=True)
    search_purpose = TSVectorField()  # Enable full-text search of purpose.
    lastchange = DateTimeTZField(default=time_now)
    suiteimplementation = CharField(max_length=255, null=True)
    test_cases = ArrayField(null=True)  # Ordered array of TestCase.id values.
    owners = ArrayField(null=True)  # Array of user IDs
    valid = BooleanField(default=True)

    class Meta:
        table_name = 'test_suites'

    def __str__(self):
        return "TestSuite: {}".format(self.name)

    @classmethod
    def search(cls, phrase):
        q = cls.select().where(cls.name.contains(phrase.split()[0]))
        for word in phrase.split():
            q = q.orwhere(cls.purpose_search.match(word))
        return q.execute()


class TestCases(BaseModel):
    """Cache a TestCase concrete implementation for reporting purposes.
    """
    # Primary plan
    name = CharField(max_length=240, unique=True)  # a.k.a title
    purpose = TextField()  # a.k.a summary
    purpose_search = TSVectorField()  # Full-text search of purpose field.
    passcriteria = TextField(null=True)  # a.k.a expectedResult
    startcondition = TextField(null=True)
    endcondition = TextField(null=True)
    procedure = TextField(null=True)  # a.k.a instructions

    # Extra data
    attributes = BinaryJSONField(dumps=json.dumps, default=None, null=True)

    # Reviews and status notes.
    comments = TextField(null=True)

    # Running, scheduling and reporting
    testimplementation = CharField(max_length=255, null=True)  # Python path
    target_software = ForeignKeyField(null=True,
                                      model=Software, field='id')
    target_component = ForeignKeyField(null=True,
                                       model=EquipmentModel, field='id')

    # Classification
    type = EnumField(constants.TestCaseType,
                     default=constants.TestCaseType.Unknown)
    priority = EnumField(constants.Priority,
                         default=constants.Priority.Unknown)
    status = EnumField(constants.TestCaseStatus,
                       default=constants.TestCaseStatus.Unknown)
    interactive = BooleanField(default=False)
    automated = BooleanField(default=True)
#    interactive | automated | meaning
#        NO      |    NO     | Manual test, user must supply final result.
#        NO      |    YES    | Fully automated
#        YES     |    NO     | Manual test, user must supply result and data.
#        YES     |    YES    | Partially automated, needs user input.

    # Management
    lastchange = DateTimeTZField(default=time_now)
    owners = ArrayField(null=True)  # Array of user IDs
    related_issues = ArrayField(null=True)  # list of bug IDs
    time_estimate = IntervalField(null=True)
    valid = BooleanField(default=True)

    class Meta:
        table_name = 'test_cases'
        indexes = (
            (("testimplementation",), False),
        )

    def __str__(self):
        return self.name

    def attribute_get(self, attrname, default=None):
        return _attribute_get(self, attrname, default)

    def attribute_set(self, attrname, attrvalue):
        return _attribute_set(self, attrname, attrvalue)

    def attribute_del(self, attrname):
        return _attribute_del(self, attrname)

    @classmethod
    def search(cls, phrase):
        q = cls.select().where(cls.name.contains(phrase.split()[0]))
        for word in phrase.split():
            q = q.orwhere(cls.purpose_search.match(word))
        return q.execute()


class Scenario(BaseModel):
    """A scenario describes the overall test goal and arrangement. May also be
    known as a use case. Can be used as a test job, as it contains all options
    required to reproduce a test.
    """
    name = CharField(max_length=255, unique=True)
    purpose = TextField(null=True)
    purpose_search = TSVectorField()  # Enable full-text search of purpose.
    implementation = CharField(max_length=255, null=True)
    parameters = BinaryJSONField(dumps=json.dumps, default=None, null=True)
    reportname = CharField(max_length=80, null=True)
    owners = ArrayField(null=True)  # Array of user IDs
    notes = TextField(null=True)
    testbed = ForeignKeyField(column_name='testbed_id',
                              model=TestBed, field='id', null=True)
    testsuite = ForeignKeyField(column_name='testsuite_id',
                                model=TestSuites, field='id',
                                backref="scenarios", null=True)

    class Meta:
        table_name = 'scenarios'

    def __str__(self):
        return self.name

    @classmethod
    def search(cls, phrase):
        q = cls.select().where(cls.name.contains(phrase.split()[0]))
        for word in phrase.split():
            q = q.orwhere(cls.purpose_search.match(word))
        return q.execute()


class TestResults(BaseModel):
    result = EnumField(constants.TestResult)
    resulttype = EnumField(constants.TestResultType)
    rdb_uuid = UUIDField(null=True)  # Map to RDB

    # Troubleshooting and data gathering
    diagnostic = TextField(null=True)
    resultslocation = CharField(max_length=255, null=True)
    data = BinaryJSONField(dumps=json.dumps, null=True)

    # Timing history
    starttime = DateTimeTZField(index=True)
    endtime = DateTimeTZField(null=True)

    # Triage note
    note = TextField(null=True)
    valid = BooleanField(default=True)

    # Reproducibility
    testversion = CharField(max_length=255, null=True)
    arguments = CharField(max_length=255, null=True)
    target = CharField(max_length=255, null=True)  # test target spec
    dutbuild = CharField(max_length=255, null=True)  # target build or version

    # Test case and result associations.
    parent = ForeignKeyField(column_name='parent_id', null=True,
                             model='self', field='id',
                             backref="subresults")
    testcase = ForeignKeyField(column_name='testcase_id', null=True,
                               model=TestCases, field='id',
                               backref="testresults")
    testsuite = ForeignKeyField(column_name='testsuite_id', null=True,
                                model=TestSuites, field='id',
                                backref="testresults")
    testbed = ForeignKeyField(column_name='testbed_id', null=True,
                              model=TestBed, field='id')

    class Meta:
        table_name = 'test_results'

    def __str__(self):
        name = ""
        if self.resulttype == constants.TestResultType.Test:
            if self.testcase:
                name = "TestCase : {}".format(self.testcase.name)
            else:
                name = "TestCase : not imported!"
        elif self.resulttype == constants.TestResultType.TestSuite:
            if self.testsuite:
                name = "TestSuite: {}".format(self.testsuite.name)
            else:
                name = "TestSuite: generic"
        elif self.resulttype == constants.TestResultType.TestRunSummary:
            name = "run id: {} on {}, artifacts: {}".format(
                self.id, self.testbed.name if self.testbed else "no testbed",
                self.resultslocation)
        else:
            name = "{!r} id: {}".format(self.resulttype, self.id)
        return "TestResult: {:10.10s} {}".format(self.result.name, name)

    @classmethod
    def get_latest_run(cls):
        r = cls.select().where((cls.starttime == cls.select(fn.MAX(cls.starttime)).where(
                (cls.resulttype == constants.TestResultType.TestRunSummary) &
                (cls.valid == True))) &  # noqa
                (cls.resulttype == constants.TestResultType.TestRunSummary)).get()
        return r

    @classmethod
    def for_testcase(cls, testcase, limit=100):
        return cls.select().where((cls.testcase == testcase) &
                                  (cls.valid == True)).order_by(cls.starttime).limit(limit).execute()  # noqa

    @classmethod
    def get_runs(cls, limit=20):
        return cls.select().where(
                    (cls.resulttype == constants.TestResultType.TestRunSummary) &
                    (cls.valid == True)  # noqa
                ).order_by(cls.starttime.desc()).limit(limit).execute()

    @classmethod
    def get_testcase_data(cls, testcase, limit=100):
        return cls.select(cls.data).where(
            (cls.resulttype == constants.TestResultType.Test) &
            (cls.testcase == testcase) & (cls.valid == True)  # noqa
            ).order_by(cls.starttime).limit(limit).execute()


def _attribute_get(inst, attrname, default=None):
    if inst.attributes is None:
        return None
    return inst.attributes.get(attrname, default)


def _attribute_set(inst, attrname, attrvalue):
    if inst.attributes is None:
        inst.attributes = {}
    with database.atomic():
        inst.attributes[attrname] = attrvalue
        inst.save()


def _attribute_del(inst, attrname):
    if inst.attributes is None:
        return
    with database.atomic():
        del inst.attributes[attrname]
        inst.save()


def connect(url=None, autocommit=False):
    """Initialize the database object to a backend database using the given URL,
    or what is configured if not provided.
    """
    global database, database_proxy
    from .util import get_database
    if database is not None:
        return
    if not url:
        from devtest import config
        cf = config.get_config()
        url = cf["database"]["url"]
    database = get_database(url, autocommit=autocommit)
    database_proxy.initialize(database)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
