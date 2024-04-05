#!/usr/bin/env python3.7
"""CPU Information and monitors.
"""

import typing


class ProcStat(typing.NamedTuple):
    """Process status.
    """
    pid: int  # process id
    ppid: int  # process id of the parent process
    pgrp: int  # pgrp of the process

    @classmethod
    def from_text(cls, bytesblob):
        res = [int(s) for s in bytesblob.split()]
        return cls(*res)

    @classmethod
    def from_pid(cls, pid):
        text = b'%d 0 0' % pid  # TODO
        return cls.from_text(text)


if __name__ == "__main__":
    import os
    ps = ProcStat.from_pid(os.getpid())
    print(ps)
#    mon = CPUUtilizationMonitor(os.getpid())
#    mon.start()
#    time.sleep(2.9)
#    for i in range(10000000):
#        x = i ** 2
#    print(mon.current())
#    mon.end()
#    del mon

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
