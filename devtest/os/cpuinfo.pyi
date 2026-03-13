from typing import NamedTuple


class ProcStat(NamedTuple):
    """Process status.

    From /proc/PID/stat, with a few fields elided.
    """
    pid: int  # process id
    ppid: int  # process id of the parent process
    pgrp: int  # pgrp of the process
    sid: int  # session id
    tty_nr: int  # tty the process uses
    tty_pgrp: int  # pgrp of the tty
    flags: int  # task flags
    min_flt: int  # number of minor faults
    cmin_flt: int  # number of minor faults with child's
    maj_flt: int  # number of major faults
    cmaj_flt: int  # number of major faults with child's
    utime: int  # user mode jiffies
    stime: int  # kernel mode jiffies
    cutime: int  # user mode jiffies with child's
    cstime: int  # kernel mode jiffies with child's
    priority: int  # priority level
    nice: int  # nice level
    num_threads: int  # number of threads
    it_real_value: int  # (obsolete, always 0)
    start_time: int  # time the process started after system boot
    vsize: int  # virtual memory size
    rss: int  # resident set memory size
    rsslim: int  # current limit in bytes on the rss
    start_code: int  # address above which program text can run
    end_code: int  # address below which program text can run
    start_stack: int  # address of the start of the main process stack
    esp: int  # current value of ESP
    eip: int  # current value of EIP
    pending: int  # bitmap of pending signals
    blocked: int  # bitmap of blocked signals
    sigign: int  # bitmap of ignored signals
    sigcatch: int  # bitmap of caught signals
    has_wchan: int  # Boolean, Has a /proc/PID/wchan entry
    exit_signal: int  # signal to send to parent thread on exit
    task_cpu: int  # which CPU the task is scheduled on
    rt_priority: int  # realtime priority
    policy: int  # scheduling policy (man sched_setscheduler)
    blkio_ticks: int  # time spent waiting for block IO
    gtime: int  # guest time of the task in jiffies
    cgtime: int  # guest time of the task children in jiffies
    start_data: int  # address above which program data+bss is placed
    end_data: int  # address below which program data+bss is placed
    start_brk: int  # address above which program heap can be expanded with brk()
    arg_start: int  # address above which program command line is placed
    arg_end: int  # address below which program command line is placed
    env_start: int  # address above which program environment is placed
    env_end: int  # address below which program environment is placed
    exit_code: int  # the thread's exit_code in the form reported by the waitpid system call

    @classmethod
    def from_text(cls, bytesblob: bytes) -> "ProcStat":
        ...

    @classmethod
    def from_pid(cls, pid: int) -> "ProcStat":
        ...
