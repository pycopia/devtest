from typing import Sized


class RingBuffer(Sized):

    def __init__(self, size: int = 65536):
        ...

    def __len__(self) -> int:
        ...

    def __getitem__(self, index: int) -> int:
        ...

    def clear(self) -> None:
        ...

    def read(self, amt: int = -1) -> bytes:
        ...

    def write(self, data: bytes) -> int:
        ...

    def fileno(self) -> int:
        ...

    size: int
    buffer: bytes
    freespace: int
    readable: bool
    writable: bool
    seekable: bool
