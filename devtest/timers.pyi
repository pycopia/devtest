from typing import Optional, Union, Tuple

CLOCK_REALTIME: int = 0
CLOCK_MONOTONIC: int = 1


def nanosleep(delay: float):
    ...


def absolutesleep(time: float, clockid: int):
    ...


def alarm(delay: float):
    ...


class FDTimer:

    def __init__(self, clockid: int = CLOCK_MONOTONIC, nonblocking: Union[int, bool] = 0):
        ...

    def settime(self, expire: float, interval: float = 0.0, absolute: Union[int, bool] = 0):
        ...

    def gettime(self) -> Tuple[float, float]:
        ...

    def read(self, amt: int = -1) -> int:
        ...

    def stop(self):
        ...


class IntervalTimer:

    def __init__(self, signo: int, clockid: int = CLOCK_MONOTONIC):
        ...

    def settime(self, expire: float, interval: float = 0.0, absolute: Union[int, bool] = 0):
        ...

    def gettime(self) -> Tuple[float, float]:
        ...

    def getoverrun(self) -> int:
        ...
