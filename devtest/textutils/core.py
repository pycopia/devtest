# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""General text functions similar to GNU core utils.
"""

import sys
import re
import binascii
import hashlib
import collections
import io
from typing import BinaryIO, TextIO

ViewType = type({}.keys())


def cut_string(s, maxlen=800):
    """Cuts a long string, returning the head and tail combined, with the
middle missing. """
    if len(s) <= maxlen:
        return s
    halflen = (min(maxlen, len(s)) // 2) - 6
    return s[:halflen] + "[...snip...]" + s[-halflen:]


def crange(start, fin):
    """like range(), but for characters."""
    for i in range(start, fin + 1):
        yield chr(i)


def grep(patt, *args):
    """grep(pattern, objects...)
returns a list of matches given an object, which should usually be a list of
strings, but could be a single string.  """
    regex = re.compile(patt)
    return list(filter(regex.search, _allargs(args)))


def cat(*args):
    """cat(obj...)
Combines all objects lines into one list."""
    return _allargs(args)


def text(*args):
    """text(object, ...)
Returns all given objects as a single string."""
    return "".join(_allargs(args))


def tac(*args):
    """tac(obj...)
Combines all objects lines into one list and returns them in reverse order."""
    l = _allargs(args)
    l.reverse()
    return l


def head(*args, n=10):
    """Returns the top n lines of the combined objects."""
    rv = []
    c = 0
    for item in _allargs(args):
        if c >= n:
            break
        rv.append(item)
        c += 1
    return rv


def tail(*args, n=10):
    """Returns the bottom 10 lines of the combined objects."""
    q = collections.deque([], n)
    for item in _allargs(args):
        q.append(item)
    return list(q)


def cksum(*args):
    """cksum(args...)
Returns the crc32 value of arguments."""
    crc = 0
    for arg in args:
        for item in _to_iter(arg):
            crc = binascii.crc32(_encode(item), crc)
    return crc


def md5sum(*args):
    "Return the MD5 sum of the arguments."
    h = hashlib.md5()
    for arg in args:
        for item in _to_iter(arg):
            h.update(_encode(item))
    return h.digest()


def sha1sum(*args):
    "Return the SHA1 sum of the arguments."
    h = hashlib.sha1()
    for arg in args:
        for item in _to_iter(arg):
            h.update(_encode(item))
    return h.digest()


def sha256sum(*args):
    "Return the SHA256 sum of the arguments."
    h = hashlib.sha256()
    for item in _allargs(args):
        h.update(_encode(item))
    return h.digest()


def sort(*args):
    """sort - Returns argument list sorted."""
    rv = list(_allargs(args))
    rv.sort()
    return rv


def uniq(*args):
    "Unique - returns the unique elements of the objects."
    return removedups(_allargs(args))


def wc(*args):
    "Word count - returns a tuple of (lines, words, characters) of the objects."
    c = w = l = 0
    for line in _allargs(args):
        c += len(line)
        w += len(line.split())
        l += 1
    return l, w, c


def nl(*args):
    "line numbers - prepends line numbers to strings in list."
    rv = []
    for n, s in enumerate(_allargs(args)):
        rv.append(f"{n + 1:6d}  {s}")
    return rv


def cut(obj, chars=None, fields=None, delim="\t"):
    """cut(obj, bytes=None, chars=None, fields=None, delim="\t")
Cut a section from the list of lines. arguments are tuples, except delim."""
    rv = []
    if chars:
        for line in _to_iter(obj):
            st, end = chars  # a 2-tuple of start and end positions
            rv.append(line[st:end])
    elif fields:
        for line in _to_iter(obj):
            words = line.split(delim)
            wl = []
            for fn in fields:
                wl.append(words[fn])
            rv.append(tuple(wl))
    else:
        raise ValueError("cut: you must specify either char range or fields")
    return rv


def hexdump(*args):
    "return a hexadecimal string representation of argument lines."
    s = []
    for line in _allargs(args):
        s.append(binascii.hexlify(_encode(line)))
    return (b"".join(s)).decode("ascii")


def removedups(s):
    """Return a list of the elements in s, but without duplicates.
    Thanks to Tim Peters for fast method.
    """
    n = len(s)
    if n == 0:
        return []
    u = {}
    try:
        for x in s:
            u[x] = 1
    except TypeError:
        del u  # move on to the next method
    else:
        return list(u.keys())
    # We can't hash all the elements.  Second fastest is to sort,
    # which brings the equal elements together; then duplicates are
    # easy to weed out in a single pass.
    try:
        t = list(s)
        t.sort()
    except TypeError:
        del t  # move on to the next method
    else:
        assert n > 0
        last = t[0]
        lasti = i = 1
        while i < n:
            if t[i] != last:
                t[lasti] = last = t[i]
                lasti = lasti + 1
            i = i + 1
        return t[:lasti]
    # Brute force is all that's left.
    u = []
    for x in s:
        if x not in u:
            u.append(x)
    return u


def flatten(*args):
    """Iterator to flatten sequences.
    """
    for alist in args:
        for val in alist:
            if isinstance(val, (list, tuple)):
                yield from flatten(val)
            elif isinstance(val, ViewType):
                yield from flatten(list(val))
            else:
                yield val


def _encode(obj):
    if isinstance(obj, bytes):
        return obj
    if isinstance(obj, str):
        return obj.encode(sys.getdefaultencoding())
    return str(obj).encode(sys.getdefaultencoding())


def _to_iter(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, bytes):
        yield obj.decode(sys.getdefaultencoding())
    elif isinstance(obj, io.IOBase) or hasattr(obj, "readlines"):
        yield from iter(obj.readlines())
    else:
        yield from iter(obj)


def _allargs(args):
    for arg in args:
        yield from _to_iter(arg)
