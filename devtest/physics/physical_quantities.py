# python3

# Physical quantities with units
#
# Written by Konrad Hinsen <hinsen@cnrs-orleans.fr>
# last revision: 2002-4-9
#

# hacked 1998/09/28 GPW: now removes __args__ from local dict after eval
#        1998/09/29 GPW: now supports conversions with offset
#                        (for temperature units)

# Modified by Keith Dart <keith@dartworks.biz>:
#     Modernized Python
#     Use numberdict
#     Added binary units (and removed "barns" unit)
#     Extended PhysicalQuantity constructor to allow easier and faster "casting".
#     Make compatible with python 3
#     Remove other external dependencies.
"""Physical quantities with units.

This module provides a data type that represents a physical
quantity together with its unit. It is possible to add and
subtract these quantities if the units are compatible, and
a quantity can be converted to another compatible unit.
Multiplication, subtraction, and raising to integer powers
is allowed without restriction, and the result will have
the correct unit. A quantity can be raised to a non-integer
power only if the result can be represented by integer powers
of the base units.

The values of physical constants are taken from the 1986
recommended values from CODATA. Other conversion factors
(e.g. for British units) come from various sources. I can't
guarantee for the correctness of all entries in the unit
table, so use this at your own risk!
"""

import re
from functools import reduce

from numpy.core import umath

from . import numberdict


class PhysicalQuantity:
    """Physical quantity with units

    Constructor:

    - PhysicalQuantity(value, unit), where `value` is a number of
      arbitrary type and `unit` is a string containing the unit name.

    - PhysicalQuantity(string), where `string` contains both the value
      and the unit. This form is provided to make interactive use more
      convenient.

    PhysicalQuantity instances allow addition, subtraction,
    multiplication, and division with each other as well as
    multiplication, division, and exponentiation with numbers.
    Addition and subtraction check that the units of the two operands
    are compatible and return the result in the units of the first
    operand. A limited set of mathematical functions (from module
    Numeric) is applicable as well:

    sqrt -- equivalent to exponentiation with 0.5.

    sin, cos, tan -- applicable only to objects whose unit is compatible
                     with 'rad'.
    """

    _NUMBER_RE = re.compile(r'([+-]?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)(\s*)(\S+)')

    def __init__(self, value, unit=None, space=" "):
        self._space = space
        if unit is not None:
            self.value = float(value)
            self.unit = _find_unit(unit)
        else:
            if isinstance(value, str):
                match = PhysicalQuantity._NUMBER_RE.match(value)
                if match is None:
                    raise TypeError(f'Not a number or number with unit: {value!r}')
                self.value = float(match.group(1))
                self._space = match.group(2)
                self.unit = _find_unit(match.group(3))
            elif isinstance(value, PhysicalQuantity):
                self.value = value.value
                self.unit = value.unit
                self._space = value._space
            elif isinstance(value, tuple):
                self.value = float(value[0])
                self.unit = _find_unit(value[1])
                try:
                    self._space = value[2]
                except IndexError:
                    pass
            else:
                raise ValueError("PhysicalQuantity can't use {!r}".format(value))

    def __str__(self):
        return "{}{}{}".format(str(self.value), self._space, self.unit.name)

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__, self.value, self.unit.name, self._space)

    # sometimes we need space printed, and sometimes we dont.
    def nospace(self):
        self._space = ""

    def usespace(self, space=" "):
        self._space = space

    def __float__(self):
        return self.value

    def _sum(self, other, sign1, sign2):
        if not isPhysicalQuantity(other):
            raise TypeError('Incompatible types')
        new_value = (sign1 * self.value +
                     sign2 * other.value * other.unit.conversion_factor_to(self.unit))
        return self.__class__(new_value, self.unit, self._space)

    def __add__(self, other):
        return self._sum(other, 1, 1)

    __radd__ = __add__

    def __sub__(self, other):
        return self._sum(other, 1, -1)

    def __rsub__(self, other):
        return self._sum(other, -1, 1)

    def __eq__(self, other):
        return self.value == other.value * other.unit.conversion_factor_to(self.unit)

    def __ne__(self, other):
        return self.value != other.value * other.unit.conversion_factor_to(self.unit)

    def __lt__(self, other):
        return self.value < other.value * other.unit.conversion_factor_to(self.unit)

    def __le__(self, other):
        return self.value <= other.value * other.unit.conversion_factor_to(self.unit)

    def __gt__(self, other):
        return self.value > other.value * other.unit.conversion_factor_to(self.unit)

    def __ge__(self, other):
        return self.value >= other.value * other.unit.conversion_factor_to(self.unit)

    def __mul__(self, other):
        if not isPhysicalQuantity(other):
            return self.__class__(self.value * other, self.unit, self._space)
        value = self.value * other.value
        unit = self.unit * other.unit
        if unit.is_dimensionless():
            return value * unit.factor
        else:
            return self.__class__(value, unit, self._space)

    __rmul__ = __mul__

    def __truediv__(self, other):
        if not isPhysicalQuantity(other):
            return self.__class__(self.value / other, self.unit, self._space)
        value = self.value / other.value
        unit = self.unit / other.unit
        if unit.is_dimensionless():
            return value * unit.factor
        else:
            return self.__class__(value, unit, self._space)

    __div__ = __truediv__

    def __rtruediv__(self, other):
        if not isPhysicalQuantity(other):
            return self.__class__(float(other) / self.value, pow(self.unit, -1), self._space)
        value = other.value / self.value
        unit = other.unit / self.unit
        if unit.is_dimensionless():
            return value * unit.factor
        else:
            return self.__class__(value, unit, self._space)

    __rdiv__ = __rtruediv__

    def __pow__(self, other):
        if isPhysicalQuantity(other):
            raise TypeError('Exponents must be dimensionless')
        return self.__class__(pow(self.value, other), pow(self.unit, other), self._space)

    def __rpow__(self, other):
        raise TypeError('Exponents must be dimensionless')

    def __abs__(self):
        return self.__class__(abs(self.value), self.unit, self._space)

    def __pos__(self):
        return self

    def __neg__(self):
        return self.__class__(-self.value, self.unit, self._space)

    def __bool__(self):
        return self.value != 0

    def to_unit(self, unit):
        """Changes the unit to `unit` and adjusts the value such that
        the combination is equivalent. The new unit is by a string containing
        its name. The new unit must be compatible with the previous unit
        of the object."""
        unit = _find_unit(unit)
        self.value = _convert_value(self.value, self.unit, unit)
        self.unit = unit

    def in_units_of(self, *units):
        """Returns one or more PhysicalQuantity objects that express
        the same physical quantity in different units. The units are
        specified by strings containing their names. The units must be
        compatible with the unit of the object. If one unit is
        specified, the return value is a single PhysicalObject. If
        several units are specified, the return value is a tuple of
        PhysicalObject instances with with one element per unit such
        that the sum of all quantities in the tuple equals the the
        original quantity and all the values except for the last one
        are integers. This is used to convert to irregular unit
        systems like hour/minute/second. The original object will not
        be changed.
        """
        units = list(map(_find_unit, units))
        if len(units) == 1:
            unit = units[0]
            value = _convert_value(self.value, self.unit, unit)
            return self.__class__(value, unit, self._space)
        else:
            units.sort()
            result = []
            value = self.value
            unit = self.unit
            for i in range(len(units) - 1, -1, -1):
                value = value * unit.conversion_factor_to(units[i])
                if i == 0:
                    rounded = value
                else:
                    rounded = _round(value)
                result.append(self.__class__(rounded, units[i]))
                value = value - rounded
                unit = units[i]
            return tuple(result)

    # Contributed by Berthold Hoellmann
    def in_base_units(self):
        new_value = self.value * self.unit.factor
        num = ''
        denom = ''
        for i in range(9):
            unit = _base_names[i]
            power = self.unit.powers[i]
            if power < 0:
                denom = denom + '/' + unit
                if power < -1:
                    denom = denom + '**' + str(-power)
            elif power > 0:
                num = num + '*' + unit
                if power > 1:
                    num = num + '**' + str(power)
        if len(num) == 0:
            num = '1'
        else:
            num = num[1:]
        return self.__class__(new_value, num + denom, self._space)

    def is_compatible(self, unit):
        unit = _find_unit(unit)
        return self.unit.is_compatible(unit)

    def sqrt(self):
        return pow(self, 0.5)

    def sin(self):
        if self.unit.is_angle():
            return umath.sin(self.value * self.unit.conversion_factor_to(_unit_table['rad']))
        else:
            raise TypeError('Argument of sin must be an angle')

    def cos(self):
        if self.unit.is_angle():
            return umath.cos(self.value * self.unit.conversion_factor_to(_unit_table['rad']))
        else:
            raise TypeError('Argument of cos must be an angle')

    def tan(self):
        if self.unit.is_angle():
            return umath.tan(self.value * self.unit.conversion_factor_to(_unit_table['rad']))
        else:
            raise TypeError('Argument of tan must be an angle')


class PhysicalUnit:

    def __init__(self, names, factor, powers, offset=0):
        if isinstance(names, str):
            self.names = numberdict.NumberDict(default=0)
            self.names[names] = 1
        else:
            self.names = names
        self.factor = float(factor)
        self.offset = offset
        self.powers = powers

    def __str__(self):
        return '<PhysicalUnit ' + self.name + '>'

    def _check(self, other):
        if self.powers != other.powers:
            raise TypeError('Incompatible units')

    def __eq__(self, other):
        self._check(other)
        return self.factor == other.factor

    def __ne__(self, other):
        self._check(other)
        return self.factor != other.factor

    def __lt__(self, other):
        self._check(other)
        return self.factor < other.factor

    def __le__(self, other):
        self._check(other)
        return self.factor <= other.factor

    def __gt__(self, other):
        self._check(other)
        return self.factor > other.factor

    def __ge__(self, other):
        self._check(other)
        return self.factor >= other.factor

    def __mul__(self, other):
        if self.offset != 0 or (isPhysicalUnit(other) and other.offset != 0):
            raise TypeError("cannot multiply units with non-zero offset")
        if isPhysicalUnit(other):
            return PhysicalUnit(self.names + other.names, self.factor * other.factor,
                                list(map(lambda a, b: a + b, self.powers, other.powers)))
        else:
            return PhysicalUnit(self.names + {str(other): 1}, self.factor * other, self.powers,
                                self.offset * other)

    __rmul__ = __mul__

    def __truediv__(self, other):
        if self.offset != 0 or (isPhysicalUnit(other) and other.offset != 0):
            raise TypeError("cannot divide units with non-zero offset")
        if isPhysicalUnit(other):
            return PhysicalUnit(self.names - other.names, self.factor / other.factor,
                                list(map(lambda a, b: a - b, self.powers, other.powers)))
        else:
            return PhysicalUnit(self.names + numberdict.NumberDict({str(other): -1}, default=0),
                                self.factor / float(other), self.powers)

    __div__ = __truediv__

    def __rtruediv__(self, other):
        if self.offset != 0 or (isPhysicalUnit(other) and other.offset != 0):
            raise TypeError("cannot divide units with non-zero offset")
        if isPhysicalUnit(other):
            return PhysicalUnit(other.names - self.names, other.factor / self.factor,
                                list(map(lambda a, b: a - b, other.powers, self.powers)))
        else:
            return PhysicalUnit({str(other): 1.} - self.names,
                                float(other) / self.factor, [-x for x in self.powers])

    __rdiv__ = __rtruediv__

    def __pow__(self, other):
        if self.offset != 0:
            raise TypeError("cannot exponentiate units with non-zero offset")
        if type(other) is int:
            return PhysicalUnit(other * self.names, pow(self.factor, other),
                                [x * other for x in self.powers])
        if type(other) is float:
            inv_exp = 1. / other
            rounded = int(umath.floor(inv_exp + 0.5))
            if abs(inv_exp - rounded) < 1.e-10:
                if reduce(lambda a, b: a and b,
                          list(map(lambda x, e=rounded: x % e == 0, self.powers))):
                    f = pow(self.factor, other)
                    p = [x / rounded for x in self.powers]
                    if reduce(lambda a, b: a and b,
                              list(map(lambda x, e=rounded: x % e == 0,
                                       list(self.names.values())))):
                        names = self.names / rounded
                    else:
                        names = numberdict.NumberDict(default=0)
                        if f != 1.:
                            names[str(f)] = 1
                        for i in range(len(p)):
                            names[_base_names[i]] = p[i]
                    return PhysicalUnit(names, f, p)
                else:
                    raise TypeError('Illegal exponent')
        raise TypeError('Only integer and inverse integer exponents allowed')

    def conversion_factor_to(self, other):
        if self.powers != other.powers:
            raise TypeError('Incompatible units')
        if self.offset != other.offset and self.factor != other.factor:
            raise TypeError('Unit conversion (%s to %s) cannot be expressed '
                            'as a simple multiplicative factor' % (self.name, other.name))
        return self.factor / other.factor

    def conversion_tuple_to(self, other):  # added 1998/09/29 GPW
        if self.powers != other.powers:
            raise TypeError('Incompatible units')

        # let (s1,d1) be the conversion tuple from 'self' to base units
        #     (ie. (x+d1)*s1 converts a value x from 'self' to base units,
        #     and (x/s1)-d1 converts x from base to 'self' units)
        # and (s2,d2) be the conversion tuple from 'other' to base units
        # then we want to compute the conversion tuple (S,D) from
        #     'self' to 'other' such that (x+D)*S converts x from 'self'
        #     units to 'other' units
        # the formula to convert x from 'self' to 'other' units via the
        #     base units is (by definition of the conversion tuples):
        #     ( ((x+d1)*s1) / s2 ) - d2
        #     = ( (x+d1) * s1/s2) - d2
        #     = ( (x+d1) * s1/s2 ) - (d2*s2/s1) * s1/s2
        #     = ( (x+d1) - (d1*s2/s1) ) * s1/s2
        #     = (x + d1 - d2*s2/s1) * s1/s2
        # thus, D = d1 - d2*s2/s1 and S = s1/s2
        factor = self.factor / other.factor
        offset = self.offset - (other.offset * other.factor / self.factor)
        return (factor, offset)

    def is_compatible(self, other):  # added 1998/10/01 GPW
        return self.powers == other.powers

    def is_dimensionless(self):
        return not reduce(lambda a, b: a or b, self.powers)

    def is_angle(self):
        return self.powers[7] == 1 and reduce(lambda a, b: a + b, self.powers) == 1

    @property
    def name(self):
        num = ''
        denom = ''
        for unit in list(self.names.keys()):
            power = self.names[unit]
            if power < 0:
                denom = denom + '/' + unit
                if power < -1:
                    denom = denom + '**' + str(-power)
            elif power > 0:
                num = num + '*' + unit
                if power > 1:
                    num = num + '**' + str(power)
        if len(num) == 0:
            num = '1'
        else:
            num = num[1:]
        return num + denom

    @name.setter
    def name(self, name):
        self.names = numberdict.NumberDict(default=0)
        self.names[name] = 1


# Type checks


def isPhysicalUnit(x):
    return isinstance(x, PhysicalUnit)


def isPhysicalQuantity(x):
    "Returns 1 if `x` is an instance of PhysicalQuantity."
    return isinstance(x, PhysicalQuantity)


# Helper functions


def _find_unit(unit):
    if isinstance(unit, (str, bytes)):
        unit = eval(unit, _unit_table)
    if not isPhysicalUnit(unit):
        raise TypeError(str(unit) + ' is not a unit')
    return unit


def _round(x):
    if umath.greater(x, 0.):
        return umath.floor(x)
    else:
        return umath.ceil(x)


def _convert_value(value, src_unit, target_unit):
    (factor, offset) = src_unit.conversion_tuple_to(target_unit)
    return (value + offset) * factor


# SI unit definitions

_base_names = ['m', 'kg', 's', 'A', 'K', 'mol', 'cd', 'rad', 'sr']

_base_units = [
    ('m', PhysicalUnit('m', 1., [1, 0, 0, 0, 0, 0, 0, 0, 0])),
    ('g', PhysicalUnit('g', 0.001, [0, 1, 0, 0, 0, 0, 0, 0, 0])),
    ('s', PhysicalUnit('s', 1., [0, 0, 1, 0, 0, 0, 0, 0, 0])),
    ('A', PhysicalUnit('A', 1., [0, 0, 0, 1, 0, 0, 0, 0, 0])),
    ('K', PhysicalUnit('K', 1., [0, 0, 0, 0, 1, 0, 0, 0, 0])),
    ('mol', PhysicalUnit('mol', 1., [0, 0, 0, 0, 0, 1, 0, 0, 0])),
    ('cd', PhysicalUnit('cd', 1., [0, 0, 0, 0, 0, 0, 1, 0, 0])),
    ('rad', PhysicalUnit('rad', 1., [0, 0, 0, 0, 0, 0, 0, 1, 0])),
    ('sr', PhysicalUnit('sr', 1., [0, 0, 0, 0, 0, 0, 0, 0, 1])),
]

_prefixes = [
    ('Y', 1.e24),
    ('Z', 1.e21),
    ('E', 1.e18),
    ('P', 1.e15),
    ('T', 1.e12),
    ('G', 1.e9),
    ('M', 1.e6),
    ('k', 1.e3),
    ('h', 1.e2),
    ('da', 1.e1),
    ('d', 1.e-1),
    ('c', 1.e-2),
    ('m', 1.e-3),
    ('u', 1.e-6),
    ('mu', 1.e-6),  # alias for mu/micro
    # ('µ',    1.e-6), # actual mu for micro, but doesn't work now
    ('n', 1.e-9),
    ('p', 1.e-12),
    ('f', 1.e-15),
    ('a', 1.e-18),
    ('z', 1.e-21),
    ('y', 1.e-24),
]

_unit_table = {}

for unit in _base_units:
    _unit_table[unit[0]] = unit[1]


def _add_unit(name, unit):
    if name in _unit_table:
        raise KeyError('Unit ' + name + ' already defined')
    if isinstance(unit, str):
        unit = eval(unit, _unit_table)
        for cruft in ['__builtins__', '__args__']:
            try:
                del _unit_table[cruft]
            except KeyError:
                pass
    unit.name = name
    _unit_table[name] = unit


def _add_prefixed(unit):
    for prefix in _prefixes:
        name = prefix[0] + unit
        _add_unit(name, prefix[1] * _unit_table[unit])


# SI derived units; these automatically get prefixes

_unit_table['kg'] = PhysicalUnit('kg', 1., [0, 1, 0, 0, 0, 0, 0, 0, 0])

_add_unit('Hz', '1./s')  # Hertz
_add_unit('N', 'm*kg/s**2')  # Newton
_add_unit('Pa', 'N/m**2')  # Pascal
_add_unit('J', 'N*m')  # Joule
_add_unit('W', 'J/s')  # Watt
_add_unit('C', 's*A')  # Coulomb
_add_unit('V', 'W/A')  # Volt
_add_unit('F', 'C/V')  # Farad
_add_unit('ohm', 'V/A')  # Ohm
_add_unit('S', 'A/V')  # Siemens
_add_unit('Wb', 'V*s')  # Weber
_add_unit('T', 'Wb/m**2')  # Tesla
_add_unit('H', 'Wb/A')  # Henry
_add_unit('lm', 'cd*sr')  # Lumen
_add_unit('lx', 'lm/m**2')  # Lux
_add_unit('Bq', '1./s')  # Becquerel
_add_unit('Gy', 'J/kg')  # Gray
_add_unit('Sv', 'J/kg')  # Sievert

del _unit_table['kg']

for unit in list(_unit_table.keys()):
    _add_prefixed(unit)

# Fundamental constants

_unit_table['pi'] = umath.pi
_add_unit('c', '299792458.*m/s')  # speed of light
_add_unit('mu0', '4.e-7*pi*N/A**2')  # permeability of vacuum
_add_unit('eps0', '1/mu0/c**2')  # permittivity of vacuum
_add_unit('Grav', '6.67259e-11*m**3/kg/s**2')  # gravitational constant
_add_unit('hplanck', '6.6260755e-34*J*s')  # Planck constant
_add_unit('hbar', 'hplanck/(2*pi)')  # Planck constant / 2pi
_add_unit('e', '1.60217733e-19*C')  # elementary charge
_add_unit('me', '9.1093897e-31*kg')  # electron mass
_add_unit('mp', '1.6726231e-27*kg')  # proton mass
_add_unit('Nav', '6.0221367e23/mol')  # Avogadro number
_add_unit('k', '1.380658e-23*J/K')  # Boltzmann constant

# Time units

_add_unit('min', '60*s')  # minute
_add_unit('h', '60*min')  # hour
_add_unit('d', '24*h')  # day
_add_unit('wk', '7*d')  # week
_add_unit('yr', '365.25*d')  # year

# Length units

_add_unit('inch', '2.54*cm')  # inch
_add_unit('in', '2.54*cm')  # inch alias
_add_unit('ft', '12*inch')  # foot
_add_unit('yd', '3*ft')  # yard
_add_unit('mi', '5280.*ft')  # (British) mile
_add_unit('nmi', '1852.*m')  # Nautical mile
_add_unit('Ang', '1.e-10*m')  # Angstrom
_add_unit('lyr', 'c*yr')  # light year
_add_unit('Bohr', '4*pi*eps0*hbar**2/me/e**2')  # Bohr radius

# Area units

_add_unit('ha', '10000*m**2')  # hectare
_add_unit('acres', 'mi**2/640')  # acre

# Volume units

_add_unit('l', 'dm**3')  # liter
_add_unit('dl', '0.1*l')
_add_unit('cl', '0.01*l')
_add_unit('ml', '0.001*l')
_add_unit('tsp', '4.92892159375*ml')  # teaspoon
_add_unit('tbsp', '3*tsp')  # tablespoon
_add_unit('floz', '2*tbsp')  # fluid ounce
_add_unit('cup', '8*floz')  # cup
_add_unit('pt', '16*floz')  # pint
_add_unit('qt', '2*pt')  # quart
_add_unit('galUS', '4*qt')  # US gallon
_add_unit('galUK', '4.54609*l')  # British gallon

# Mass units

_add_unit('amu', '1.6605402e-27*kg')  # atomic mass units
_add_unit('oz', '28.349523125*g')  # ounce
_add_unit('lb', '16*oz')  # pound
_add_unit('ton', '2000*lb')  # ton

# Force units

_add_unit('dyn', '1.e-5*N')  # dyne (cgs unit)
_add_unit('lbF', 'lb*32.17405*ft/s**2')  # pound-force
_add_unit('ozF', 'lbF*0.0625')  # ounce-force
_add_unit('kgF', '9.80665*N')  # kilogram-force
_add_unit('gF', '0.00980665*N')  # gram-force

# Energy units

_add_unit('erg', '1.e-7*J')  # erg (cgs unit)
_add_unit('eV', 'e*V')  # electron volt
_add_prefixed('eV')
_add_unit('Hartree', 'me*e**4/16/pi**2/eps0**2/hbar**2')
_add_unit('invcm', 'hplanck*c/cm')  # Wavenumbers/inverse cm
_add_unit('Ken', 'k*K')  # Kelvin as energy unit
_add_unit('cal', '4.184*J')  # thermochemical calorie
_add_unit('kcal', '1000*cal')  # thermochemical kilocalorie
_add_unit('cali', '4.1868*J')  # international calorie
_add_unit('kcali', '1000*cali')  # international kilocalorie
_add_unit('Btu', '1055.05585262*J')  # British thermal unit

# Power units

_add_unit('hp', '745.7*W')  # horsepower

# Pressure units

_add_unit('bar', '1.e5*Pa')  # bar (cgs unit)
_add_unit('atm', '101325.*Pa')  # standard atmosphere
_add_unit('torr', 'atm/760')  # torr = mm of mercury
_add_unit('psi', '6894.75729317*Pa')  # pounds per square inch

# Angle units

_add_unit('deg', 'pi*rad/180')  # degrees

# Temperature units -- can't use the 'eval' trick that _add_unit provides
# for degC and degF because you can't add units
kelvin = _find_unit('K')
_add_unit('degR', '(5./9.)*K')  # degrees Rankine
_add_unit('degC', PhysicalUnit(None, 1.0, kelvin.powers, 273.15))
_add_unit('degF', PhysicalUnit(None, 5. / 9., kelvin.powers, 459.67))
del kelvin

# binary prefixes
_prefixes.extend([
    ("Ki", 1024.0),
    ("Mi", 1048576.0),
    ("Gi", 1073741824.0),
    ("Ti", 1099511627776.0),
    ("Pi", 1125899906842624.0),
])

# counted objects used in technology
_add_unit('n', '1.*mol')  # An N count of anything unitless (packets, etc.)
_add_unit('b', 'mol')  # bit
_add_unit('B', '8*b')  # Byte
_add_prefixed('b')
_add_prefixed('B')

if __name__ == '__main__':
    small_l = PhysicalQuantity(10., 'm')
    big_l = PhysicalQuantity(10., 'km')
    print(big_l + small_l)
    t = PhysicalQuantity(314159., 's')
    print(t.in_units_of('d', 'h', 'min', 's'))

    p = PhysicalQuantity  # just a shorthand...

    print("add us:", p("1.0", "us") + p("1.0", "us"))  # "µs") )
    e = p('2.7 Hartree*Nav')
    e.to_unit('kcal/mol')
    print(e)
    print(e.in_base_units())

    freeze = p('0 degC')
    print(freeze.in_units_of('degF'))

    kb = p(1000, "b")
    r = kb / p(1.0, "s")
    print(r)
    print(r.in_units_of("B/s"))

    Kibit = p(1.0, "Kib")
    print(Kibit)
    print(Kibit.in_units_of("B"))
    assert Kibit.in_units_of("B").value == 1024 / 8
    # 100 kB = 97.65625 KiB
    print(p(100, "kB").in_units_of("KiB"))
    assert p(100, "kB").in_units_of("Kib").value == 97.65625 * 8

    PACKET = p(1.0, "n")

    packets = 12.0 * PACKET
    print(packets / p(1., "s"))
    avgpack = p(40., "B") / PACKET
    avgrate = (packets * avgpack) / p(1., "s")
    print(avgrate.in_units_of("B/s"))
    assert avgrate.in_units_of("b/s").value == (12.0 * 40.0 * 8)
    print(PhysicalQuantity((10., "m")))
    assert PhysicalQuantity(avgrate) == avgrate
    assert str(PhysicalQuantity("10ms")) == "10.0ms"
    assert str(PhysicalQuantity("10 ms")) == "10.0 ms"
    # conversions and comparisons
    assert p(.9, "m") == p(90, "cm")
    assert p(3.5, "inch") == p(8.89, "cm")
    assert p(1., "qt") < p(947., "ml")
    assert p(1.1, "qt") > p(947., "ml")
