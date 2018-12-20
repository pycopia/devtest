# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom field definitions for Peewee and Postgresql."""

import enum
import ipaddress
from datetime import timedelta

from peewee import Field
from playhouse.postgres_ext import (BinaryJSONField, TSVectorField,  # noqa
                                    DateTimeTZField, ArrayField)

from devtest.core import types

JSONField = BinaryJSONField

_PEEWEE_FIELDS = ['BareField', 'BigIntegerField', 'BlobField',
                  'BooleanField', 'CharField', 'DateField', 'DateTimeField',
                  'DecimalField', 'DoubleField', 'FixedCharField',
                  'FloatField', 'ForeignKeyField', 'IntegerField',
                  'AutoField', 'TextField', 'TimeField', 'UUIDField']


# Peewee is monolithic
def _import_peewee_fields():
    import peewee
    import sys
    me = sys.modules[__name__]
    for name in _PEEWEE_FIELDS:
        obj = getattr(peewee, name)
        setattr(me, name, obj)


_import_peewee_fields()
del _import_peewee_fields

__all__ = ['IPv4Field', 'IPv6Field', 'CIDRField', 'MACField', 'EnumField',
           'IntervalField', 'TSVectorField', 'DateTimeTZField', 'ArrayField',
           'BinaryJSONField', 'JSONField'] + _PEEWEE_FIELDS


class IPv4Field(Field):
    """A field for an IP address that may be a host address."""
    field_type = 'inet'

    def db_value(self, value):
        return None if value is None else str(value)

    def python_value(self, value):
        return None if value is None else ipaddress.IPv4Interface(value)


class IPv6Field(Field):
    """A field for an IPv6 network address."""
    field_type = 'inet'

    def db_value(self, value):
        return None if value is None else str(value)

    def python_value(self, value):
        return None if value is None else ipaddress.IPv6Interface(value)


class CIDRField(Field):
    """A field for an IP network address."""
    field_type = 'cidr'

    def db_value(self, value):
        return None if value is None else str(value)

    def python_value(self, value):
        return None if value is None else ipaddress.IPv4Network(value)


class MACField(Field):
    """A field for an MAC layer address."""
    field_type = 'macaddr'

    def db_value(self, value):
        return None if value is None else str(value)

    def python_value(self, value):
        return None if value is None else types.MACAddress(value)


class EnumField(Field):
    """A field for storing enum.IntEnum objects as an Integer."""
    field_type = 'int'

    def __init__(self, enumclass, default=None, help_text=None,
                 verbose_name=None, **extra):
        assert issubclass(enumclass, enum.IntEnum)
        self._eclass = enumclass
        choices = [(e.value, e.name) for e in enumclass]
        kwargs = {
            "verbose_name": verbose_name or enumclass.__name__,
            "choices": choices,
            "default": choices[0][0] if default is None else default,
            "help_text": help_text}
        kwargs.update(extra)
        super().__init__(**kwargs)

    def db_value(self, value):
        return None if value is None else int(value)

    def python_value(self, value):
        return None if value is None else self._eclass(value)

    def clone_base(self, **kwargs):
        return super().clone_base(enumclass=self._eclass, **kwargs)


class IntervalField(Field):
    """Time intervals get and receive timedelta objects, or integer as seconds.
    """
    field_type = 'bigint'

    def db_value(self, value):
        if value is None:
            return None
        if isinstance(value, timedelta):
            return value.days * 86400 + value.seconds
        else:
            return int(value)

    def python_value(self, value):
        return None if value is None else timedelta(seconds=value)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
