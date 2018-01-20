"""
Support for iterating of combinations of sets.
"""

from __future__ import generator_stop


from functools import reduce


def factorial(x):
    """return x!
    """
    return x <= 0 or reduce(lambda a, b: a * b, range(1, x + 1))


def prune_end(n, l):
    return l[:n]


class ListCounter:
    """An iterator that counts through its list of lists."""
    def __init__(self, lists):
        self._lists = lists
        self._lengths = [len(l) for l in lists]
        if self._lengths.count(0) > 0:
            raise ValueError("All lists must have at least one element.")
        self._places = len(self._lengths)
        self.reset()

    def reset(self):
        self._counters = [0] * self._places
        self._counters[0] -= 1

    def __iter__(self):
        self.reset()
        return self

    def __next__(self):
        self._increment(0)
        return self.fetch()

    def _increment(self, place):
        carry, self._counters[place] = divmod(self._counters[place] + 1,
                                              self._lengths[place])
        if carry:
            if place + 1 < self._places:
                return self._increment(place + 1)
            else:
                raise StopIteration
        return carry

    def fetch(self):
        return [l[i] for l, i in zip(self._lists, self._counters)]

    def get_number(self):
        return reduce(lambda a, b: a * b, self._lengths, 1)


class KeywordCounter:
    def __init__(self, **kwargs):
        self._names = list(kwargs.keys())
        values = list(kwargs.values())  # All values should be sequences
        assert all(isinstance(val, list) for val in values)
        self._counter = ListCounter(values)

    def prune(self, maxN, chooser=prune_end):
        lists = prune(maxN, self._counter._lists, chooser)
        self._counter = ListCounter(lists)

    def __iter__(self):
        self._counter.reset()
        return self

    def __next__(self):
        values = next(self._counter)  # The ListCounter will raise StopIteration
        return self.fetch(values)

    def get_number(self):
        return self._counter.get_number()

    def fetch(self, values):
        return dict(zip(self._names, values))


def prune(maxN, sets, chooser=prune_end):
    """Prune a collection of sets such that number of combinations is less than
    or equal to maxN.  Use this to set an upper bound on combinations and you
    don't care if you "hit" all combinations.  This simple algorithm basically
    reduces the number of entries taken from the largest set. If then are equal
    numbered, then removal is left to right.

    maxN is the maximum number of combinations.
    sets is a list of lists containing the items to be combined.
    chooser implements the pruning policy. It should be a function taking a
    number, N, and a list and returning a new list with N elements.
    """
    lenlist = [len(l) for l in sets]
    while reduce(lambda a, b: a * b, lenlist, 1) > maxN:
        lv, li = maxi(lenlist)
        lenlist[li] -= 1
    return [chooser(n, l) for n, l in zip(lenlist, sets)]


def maxi(seq):
    cmax = seq[0]
    ci = 0
    for i, val in enumerate(seq):
        if val > cmax:
            cmax = val
            ci = i
    return cmax, ci


if __name__ == "__main__":
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(2) == 2
    assert factorial(3) == 6
    assert factorial(10) == 3628800

    # 10*5*2 = 100
    s1 = list(range(10))
    s2 = list(range(5))
    s3 = list(range(2))
    lc = ListCounter(prune(60, [s1, s2, s3]))
    assert lc.get_number() == 60
    for i, l in enumerate(lc):
        print("%02d. %s" % (i, l))

    kc = KeywordCounter(arg1=s1, arg2=s2, arg3=s3)
    print(kc.get_number())
    for kwargs in kc:
        print(kwargs)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
