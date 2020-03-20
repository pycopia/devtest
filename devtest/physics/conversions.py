# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""General conversion functions.

Convert units from one to another. Generally you can use a PhysicalQuantity
object to do linear conversions. But that doesn't handle logarithmic units yet.

All voltages are RMS values.
"""

import math


def dBVToVolts(dbv):
    return 10.0**(dbv / 20.0)


def VoltsTodBV(v):
    return 20.0 * math.log10(v / 1.0)


def VoltsTodBu(v):
    return 20.0 * math.log10(v / 0.77459667)


def dBuToVolts(dbu):
    return 0.77459667 * 10.0**(dbu / 20.0)


def dBmToWatts(dbm):
    return 0.001 * 10.0**(dbm / 10.0)


def WattsTodBm(w):
    return 10.0 * math.log10(w / 0.001)


def degCToDegF(t):
    return (t * 9) / 5 + 32


def degFToDegC(t):
    return (t - 32) * 5 / 9
