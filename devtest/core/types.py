# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Various extra basic types for use by the framework.
"""

# Use the newer built-in enums for Enum. Here we will always use Integer Enums.
from enum import IntEnum as Enum  # noqa


class NULLType(type):
    """Similar to None, but is also a no-op callable and empty iterable.
    """

    def __new__(cls, name, bases, dct):
        return type.__new__(cls, name, bases, dct)

    def __init__(cls, name, bases, dct):
        super(NULLType, cls).__init__(name, bases, dct)

    def __reduce__(self):
        return (NULLType, ("NULL", (), {}))

    def __str__(self):
        return ""

    def __repr__(self):
        return "NULL"

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __call__(self, *args, **kwargs):
        return None

    def __contains__(self, item):
        return False

    def __iter__(self):
        return self

    def __next__(*args):
        raise StopIteration


NULL = NULLType("NULL", (), {})


class NamedNumber(int):
    """A named number. Behaves as an integer, but produces a name when
    stringified.
    """

    def __new__(cls, val, name=None):
        v = int.__new__(cls, val)
        v._name = str(name)
        return v

    def __getstate__(self):
        return int(self), self._name

    def __setstate__(self, args):
        i, self._name = args

    def __str__(self):
        return self._name

    def __repr__(self):
        return "{}({:d}, {!r})".format(self.__class__.__name__, self, self._name)


class NamedNumberSet(list):
    """A list of NamedNumber objects."""

    def __init__(self, *init, **kwinit):
        for i, val in enumerate(init):
            if isinstance(val, list):
                for j, subval in enumerate(val):
                    self.append(NamedNumber(i * j, str(subval)))
            elif isinstance(val, NamedNumber):
                self.append(val)
            else:
                self.append(NamedNumber(i, str(val)))
        for name, value in list(kwinit.items()):
            enum = NamedNumber(int(value), name)
            self.append(enum)
        self.sort()

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, list.__repr__(self))

    def find(self, value):
        """Find the NamedNumber with the given value."""
        i = self.index(int(value))
        return self[i]


class AttrDict(dict):
    """A dictionary with attribute-style access. It maps attribute access to
    the real dictionary.  """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    def __getstate__(self):
        return list(self.__dict__.items())

    def __setstate__(self, items):
        for key, val in items:
            self.__dict__[key] = val

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, dict.__repr__(self))

    def __setitem__(self, key, value):
        return super(AttrDict, self).__setitem__(key, value)

    def __getitem__(self, name):
        return super(AttrDict, self).__getitem__(name)

    def __delitem__(self, name):
        return super(AttrDict, self).__delitem__(name)

    __getattr__ = __getitem__
    __setattr__ = __setitem__

    def copy(self):
        return AttrDict(self)


class AttrDictDefault(dict):
    """A dictionary with attribute-style access. It maps attribute access to
    the real dictionary. Returns a default entry if key is not found. """

    def __init__(self, init={}, default=None):
        dict.__init__(self, init)
        self.__dict__["_default"] = default

    def __getstate__(self):
        return list(self.__dict__.items())

    def __setstate__(self, items):
        for key, val in items:
            self.__dict__[key] = val

    def __repr__(self):
        return "%s(%s, %r)" % (self.__class__.__name__, dict.__repr__(self),
                               self.__dict__["_default"])

    def __setitem__(self, key, value):
        return super(AttrDictDefault, self).__setitem__(key, value)

    def __getitem__(self, name):
        try:
            return super(AttrDictDefault, self).__getitem__(name)
        except KeyError:
            return self.__dict__["_default"]

    def __delitem__(self, name):
        return super(AttrDictDefault, self).__delitem__(name)

    __getattr__ = __getitem__
    __setattr__ = __setitem__

    def copy(self):
        return self.__class__(self, self.__dict__["_default"])

    def get(self, name, default=None):
        df = default or self.__dict__["_default"]
        return super(AttrDictDefault, self).get(name, df)


class MACAddress:
    """MAC addressess."""

    def __init__(self, mac):
        self.mac = str(mac)

    def __str__(self):
        return self.mac


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
