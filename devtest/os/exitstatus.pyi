import signal


class ExitStatus:
    """Common exit status object for subprocesses and devices.

    Can be avaluated for truthiness and will avaluate True only if status
    indicates a normal process exit. A normal exit is zero, but this will still
    evaluate True. It works the same as a typical posix shell.
    """

    def __init__(self, sts: int | None, name: str = "unknown", returncode: int | None = None):
        ...

    @property
    def status(self) -> int:
        ...

    @property
    def signal(self) -> signal.Signals:
        ...

    def exited(self) -> bool:
        ...

    def stopped(self) -> bool:
        ...

    def signalled(self) -> bool:
        ...

    def __int__(self) -> int:
        ...

    def __bool__(self) -> bool:
        ...
