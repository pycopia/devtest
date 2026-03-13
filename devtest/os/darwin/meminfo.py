"""Memory info for Darwin.
"""
# TODO

from collections import namedtuple

MemUsage = namedtuple("MemUsage", [
    "Size", "KernelPageSize", "MMUPageSize", "Rss", "Pss", "Uss", "Shared_Clean", "Shared_Dirty",
    "Private_Clean", "Private_Dirty", "Referenced", "Anonymous", "LazyFree", "AnonHugePages",
    "ShmemPmdMapped", "Shared_Hugetlb", "Private_Hugetlb", "Swap", "SwapPss", "Locked", "VmFlags"
])


class VirtualMemoryArea:
    pass


class Maps(list):
    """A list of `VirtualMemoryArea`s.
    """

    @classmethod
    def from_text(cls, bytesblob):
        pass  # TODO
