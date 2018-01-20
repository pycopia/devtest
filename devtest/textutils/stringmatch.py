"""
Match plain strings like they were re module objects.

The StringExpression object implements a subset of re compile expressions.
This allows for a more consistent interface for the match types.  Since
string.find is about 10 times faster than an RE search with a plain string,
this should speed up matches in that case by about that much, while
keeping a consistent interface.
"""


class StringMatchObject:
    def __init__(self, start, end, string, pos, endpos, re):
        self._start = start
        self._end = end
        self.string = string
        self.pos = pos
        self.endpos = endpos
        self.lastgroup = None
        self.lastindex = None
        self.re = re  # not really an RE.

    def __repr__(self):
        return ("{0}(start={1!r}, end={2!r}, string={3!r}, pos={4!r}, "
                "endpos={5!r}, re={6!r})").format(
                    self.__class__.__name__, self._start, self._end,
                    self.string, self.pos, self.endpos, self.re)

    def expand(self, template):
        raise NotImplementedError("Not applicable to plain strings")

    def group(self, *args):
        if args and args[0] == 0:
            return self.string[self._start:self._end]
        else:
            raise IndexError("no such group")

    def groups(self, default=None):
        return ()

    def groupdict(self, default=None):
        return {}

    def start(self, group=0):
        if group == 0:
            return self._start
        else:
            raise IndexError("no such group")

    def end(self, group=0):
        if group == 0:
            return self._end
        else:
            raise IndexError("no such group")

    def span(self, group=0):
        if group == 0:
            return self._start, self._end
        else:
            return -1, -1

    def __bool__(self):
        return True


# an object that looks like a compiled regular expression, but does exact
# string matching. This is usually much faster in that case.
class StringExpression:
    def __init__(self, patt, flags=0):
        self.pattern = patt
        # bogus attributes to simulate compiled REs from re module.
        self.flags = flags
        self.groupindex = {}

    def __repr__(self):
        return "{0}(patt={1!r}, flags={2!r})".format(
            self.__class__.__name__, self.pattern, self.flags)

    def search(self, text, pos=0, endpos=2147483647):
        n = text.find(self.pattern, pos, endpos)
        if n >= 0:
            return StringMatchObject(
                n, n + len(self.pattern), text, pos, endpos, self)
        else:
            return None
    match = search  # match is same as search for strings

    def split(self, text, maxsplit=0):
        return text.split(self.pattern, maxsplit)

    def findall(self, string, pos=0, endpos=2147483647):
        rv = []
        i = 0
        while i >= 0:
            i = string.find(self.pattern, i)
            if i >= 0:
                rv.append(self.pattern)
        return rv

    def finditer(self, string, pos=0, endpos=2147483647):
        while 1:
            mo = self.search(string, pos, endpos)
            if mo:
                yield mo
            else:
                return

    def sub(self, repl, string, count=2147483647):
        return string.replace(self.pattern, repl, count)

    def subn(self, repl, string, count=2147483647):
        i = 0
        N = 0
        while i >= 0:
            i = string.find(self.pattern, i)
            if i >= 0:
                N += 1
        return string.replace(self.pattern, repl, count), N


# factory function to "compile" EXACT patterns (which are strings)
def compile_exact(string, flags=0):
    return StringExpression(string, flags)


def _test(argv):
    cs = compile_exact("me")
    mo = cs.search("matchme")
    assert mo is not None
    print(mo.span())
    assert mo.span() == (5, 7)
    assert mo.string == "matchme"

    cs = compile_exact(b"me")
    mo = cs.search(b"matchme")
    assert mo is not None
    print(mo.span())
    assert mo.span() == (5, 7)
    assert mo.string == b"matchme"


if __name__ == "__main__":
    import sys
    _test(sys.argv)
