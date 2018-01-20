"""
Custom form fields. All available form field definitions are available here.

"""

from __future__ import generator_stop

import ipaddress

from wtforms import widgets
# Retain this import order. Some fields have the same name as simpler versions
# and this will make the nicer ones overwrite simple ones.
from wtforms.fields.core import *  # noqa
from wtforms.fields.simple import *  # noqa
from wtforms.fields.html5 import *  # noqa
from wtfpeewee.fields import *  # noqa

from devtest import json

# Current (Aug 15) field selection.

__all__ = ['ArrayField', 'AttributesField', 'BooleanField', 'BooleanSelectField',
           'CIDRField', 'DateField', 'DateTimeField', 'DateTimeLocalField',
           'DecimalField', 'DecimalRangeField', 'EmailField', 'EnumField',
           'FieldList', 'FileField', 'FloatField', 'FormField', 'HTMLField',
           'HiddenField', 'HiddenQueryField', 'IPv4Field', 'IPv6Field',
           'IntegerField', 'IntegerRangeField', 'IntervalField', 'JSONField',
           'MACField', 'ModelHiddenField', 'ModelSelectField',
           'ModelSelectMultipleField', 'PasswordField', 'RadioField',
           'SearchField', 'SelectChoicesField', 'SelectField',
           'SelectMultipleField', 'SelectMultipleQueryField',
           'SelectQueryField', 'StringField', 'SubmitField', 'TelField',
           'TextAreaField', 'TextField', 'URLField', 'WPDateField',
           'WPDateTimeField', 'WPTimeField', ]


class IPv4Field(StringField):

    def process_formdata(self, valuelist):
        if valuelist:
            val = valuelist[0]
            try:
                self.data = ipaddress.IPv4Address(val)
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
                raise ValueError('{!r} is not a valid IPv4 address'.format(val))


class IPv6Field(StringField):

    def process_formdata(self, valuelist):
        if valuelist:
            val = valuelist[0]
            try:
                self.data = ipaddress.IPv6Address(val)
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
                raise ValueError('{!r} is not a valid IPv6 address'.format(val))


class CIDRField(StringField):

    def process_formdata(self, valuelist):
        if valuelist:
            val = valuelist[0]
            try:
                self.data = ipaddress.IPv4Network(val)
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
                raise ValueError('{!r} is not a valid IPv4 network'.format(val))


class MACField(StringField):
    pass


class EnumField(SelectChoicesField):

    def iter_choices(self):
        for value, label in self.choices:
            yield value, label, True if value == self.data else False

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = int(valuelist[0])


class JSONField(TextAreaField):

    def process_data(self, value):
        self.data = json.encode(value)

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = json.decode(valuelist[0])
        else:
            self.data = None


class UUIDField(StringField):
    pass


class HTMLWidget:
    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        return '<textarea {}>{}</textarea>'.format(widgets.html_params(name=field.name, **kwargs),
                                                   field._value())


class HTMLField(TextAreaField):
    widget = HTMLWidget()


class AttributesField(FieldList):
    widget = widgets.TableWidget()


class ArrayField(FieldList):
    widget = widgets.TableWidget()


class IntervalField(IntegerField):
    pass


def _test(argv):
    ec = EnumField(choices=[(1, "one"), (2, "two")])
    print(ec)


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
