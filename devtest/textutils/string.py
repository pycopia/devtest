# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Additional string helper functions and constants.
"""

import keyword

# ASCII values
lowercase = 'abcdefghijklmnopqrstuvwxyz'
uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
digits = '0123456789'
hexdigits = '0123456789ABCDEF'
letters = lowercase + uppercase
alphanumeric = lowercase + uppercase + digits
whitespace = ' \t\n\r\v\f'
punctuation = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
printable = digits + letters + punctuation + whitespace
control = "".join(map(chr, range(32))) + chr(127)
ascii = control + " " + digits + letters + punctuation

CR = "\r"
LF = "\n"
CRLF = CR + LF
ESCAPE = chr(27)
DEL = chr(127)

tbl = ["_"] * 256
for c in letters:
    tbl[ord(c)] = c
for c in digits:
    tbl[ord(c)] = c
_IDENTTABLE = "".join(tbl)
del tbl, c

_KEYWORDS = {}
for kw in keyword.kwlist:
    _KEYWORDS[kw] = kw + "_"
del kw, keyword


def identifier(name, asclass=False):
    """Return a valid Python identifier given an arbitrary string."""
    ident = name.translate(_IDENTTABLE)
    if asclass:
        return ''.join(x.capitalize() for x in ident.split("_"))
    return _KEYWORDS.get(ident, ident)


if __name__ == "__main__":
    assert identifier("test me") == "test_me"
    assert identifier("class") == "class_"
    assert identifier("class", asclass=True) == "Class"
    assert identifier("some class name", asclass=True) == "SomeClassName"
