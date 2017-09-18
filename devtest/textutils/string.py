"""
Additional string helper functions.
"""

import keyword

ascii_lowercase = 'abcdefghijklmnopqrstuvwxyz'
ascii_uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
ascii_letters = ascii_lowercase + ascii_uppercase
digits = '0123456789'


tbl = ["_"] * 256
for c in ascii_letters:
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
    """Return a valid Python keyword identifier given an arbitrary string."""
    ident = name.translate(_IDENTTABLE)
    if asclass:
        return ''.join(x.capitalize() for x in ident.split("_"))
    return _KEYWORDS.get(ident, ident)


if __name__ == "__main__":
    assert identifier("test me") == "test_me"
    assert identifier("class") == "class_"
    assert identifier("class", asclass=True) == "Class"
    assert identifier("some class name", asclass=True) == "SomeClassName"

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
