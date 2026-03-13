import pwd

from devtest.os.exitstatus import ExitStatus


def run_as(pwent: pwd.struct_passwd, umask: int = 0o22) -> None:
    ...


def system(cmd: str) -> ExitStatus:
    ...


def which(basename: str) -> str | None:
    ...
