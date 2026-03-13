from typing import Optional, NamedTuple


class VmFlags:

    def __init__(self, flags: str):
        ...


class MemUsage(NamedTuple):
    Size: int
    KernelPageSize: int
    MMUPageSize: int
    Rss: int
    Pss: int
    Uss: int  # computed value
    Pss_Dirty: int
    Shared_Clean: int
    Shared_Dirty: int
    Private_Clean: int
    Private_Dirty: int
    Referenced: int
    Anonymous: int
    KSM: int
    LazyFree: int
    AnonHugePages: int
    ShmemPmdMapped: int
    FilePmdMapped: int
    Shared_Hugetlb: int
    Private_Hugetlb: int
    Swap: int
    SwapPss: int
    Locked: int
    THPeligible: bool
    VmFlags: str | None


class VirtualMemoryArea:
    """A memory mapped area of a process.

    Attributes:
        name: str  Name of mapping (may not exist)
        start: int  Address of start of range
        end: int  Address of end of range
        offset: int  Offset into mapped file, if any
        perms: str  Permissions of area
        device: str Device node, if any
        inode: int  Inode of mapped file, if any.
        usage: A MemUsage instance.

    The permissions are:
        r = read
        w = write
        x = execute
        s = shared
        p = private (copy on write)
    """

    def __init__(self, name: str, start: int, end: int, offset: int, perms: str, device: str, inode:
                 int, usage: Optional[MemUsage] = None):
        ...


class Maps(list):
    """A list of `VirtualMemoryArea`s.
    """

    @classmethod
    def from_text(cls, bytesblob: bytes):
        ...


class MemoryMonitor:
    """Aid monitoring memory usage of a process over a span of time.

    Call start method, wait some time, then call the stop method.
    Use the difference method to get a MemUsage with fields set to the
    difference of the stop and start values.
    """

    def __init__(self, pid: int | None = None):
        ...
