# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Replacement logging module. This module is light, and intended to leverage the
system's syslog service. Log destination configuration should be done there.

Why use this instead of the "stock" logging module?

- Speed. We want logging messages to get to the system logger as fast as
  possible. No other processing is necessary.
- Consistency. No need to duplicate formatting functionality. The global string
  formatting is sufficient.
- Simplicity. No extra configuration. All logging configuration is done in one
  place, at the system logger. See `man syslogd`.

Configurable with the following environment variables:

DEVTEST_LOG_FACILITY
    Sets the syslog facility to use, default USER.

DEVTEST_LOG_PRIORITY
    Sets the syslog priority to log, default NOTICE.

DEVTEST_LOG_STDERR
    Set to include stderr in log output.


When this module is imported it monkey-patches the stock logging module to use this module, and sets
up a syslog handler.
"""

import sys
import os
import syslog
from typing import Optional, Dict

# also import and configure standard logging here. This module will override the root logger.
# This module should be imported first.
import logging

FACILITY: str = os.environ.get("DEVTEST_LOG_FACILITY", "USER").upper()
PRIORITY: str = os.environ.get("DEVTEST_LOG_PRIORITY", "NOTICE").upper()
USESTDERR: bool = bool(os.environ.get("DEVTEST_LOG_STDERR"))

_oldpriority = 0


def openlog(ident=None, usestderr=USESTDERR, facility=FACILITY):
    opts = syslog.LOG_PID | (syslog.LOG_PERROR if usestderr else 0)
    if isinstance(facility, str):
        facility = getattr(syslog, "LOG_" + facility.upper())
    if ident is None:  # openlog does not take None as an ident parameter.
        syslog.openlog(logoption=opts, facility=facility)
    else:
        syslog.openlog(ident=ident, logoption=opts, facility=facility)


def closelog():
    syslog.closelog()


def debug(msg, *args):
    syslog.syslog(syslog.LOG_DEBUG, _encode(msg, args))


def info(msg, *args):
    syslog.syslog(syslog.LOG_INFO, _encode(msg, args))


def notice(msg, *args):
    syslog.syslog(syslog.LOG_NOTICE, _encode(msg, args))


def warning(msg, *args):
    syslog.syslog(syslog.LOG_WARNING, _encode(msg, args))


def error(msg, *args):
    syslog.syslog(syslog.LOG_ERR, _encode(msg, args))


def critical(msg, *args):
    syslog.syslog(syslog.LOG_CRIT, _encode(msg, args))


def alert(msg, *args):
    syslog.syslog(syslog.LOG_ALERT, _encode(msg, args))


def emergency(msg, *args):
    syslog.syslog(syslog.LOG_EMERG, _encode(msg, args))


def _encode(o, args):
    # Add UTF8 BOM to message per RFC-5424. str is UTF-8 encoded by syslog module.
    if args:
        return '\ufeff' + (str(o) % args)
    return '\ufeff' + str(o)


def set_priority(level):
    """Set syslog priority.

    Args:
        level: syslog.LOG_* level.
    """
    global _oldpriority
    _oldpriority = syslog.setlogmask(syslog.LOG_UPTO(level))
    logging.root.level = _LOGGING_LEVELS[PRIORITIES_REV[level]]


def get_priority():
    """Get max syslog priority."""
    mask = syslog.setlogmask(0)
    for level in (syslog.LOG_DEBUG, syslog.LOG_INFO, syslog.LOG_NOTICE, syslog.LOG_WARNING,
                  syslog.LOG_ERR, syslog.LOG_CRIT, syslog.LOG_ALERT, syslog.LOG_EMERG):
        if syslog.LOG_MASK(level) & mask:
            return level


def priority_restore():
    syslog.setlogmask(_oldpriority)
    logging.root.level = _LOGGING_LEVELS[PRIORITIES_REV[_oldpriority]]


def priority_debug():
    set_priority(syslog.LOG_DEBUG)


def priority_info():
    set_priority(syslog.LOG_INFO)


def priority_notice():
    set_priority(syslog.LOG_NOTICE)


def priority_warning():
    set_priority(syslog.LOG_WARNING)


def priority_error():
    set_priority(syslog.LOG_ERR)


def priority_critical():
    set_priority(syslog.LOG_CRIT)


def priority_alert():
    set_priority(syslog.LOG_ALERT)


# common logging patterns
def exception_error(prefix, ex, *args):
    error("{}: {}".format(_encode(prefix, args), _format_exception(ex)))


def exception_warning(prefix, ex, *args):
    warning("{}: {}".format(_encode(prefix, args), _format_exception(ex)))


def _format_exception(ex):
    s = ["{} ({})".format(ex.__class__.__name__, ex)]
    orig = ex
    while ex.__context__ is not None:
        ex = ex.__context__
        s.append(" Within: {} ({})".format(ex.__class__.__name__, ex))
    ex = orig
    while ex.__cause__ is not None:
        ex = ex.__cause__
        s.append(" Cause: {} ({})".format(ex.__class__.__name__, ex))
    return " | ".join(s)


# Allow use of names, and useful aliases, to select logging level.
PRIORITIES = {
    "DEBUG": syslog.LOG_DEBUG,
    "INFO": syslog.LOG_INFO,
    "NOTICE": syslog.LOG_NOTICE,
    "WARNING": syslog.LOG_WARNING,
    "WARN": syslog.LOG_WARNING,
    "ERR": syslog.LOG_ERR,
    "ERROR": syslog.LOG_ERR,
    "CRIT": syslog.LOG_CRIT,
    "CRITICAL": syslog.LOG_CRIT,
    "ALERT": syslog.LOG_ALERT,
}
PRIORITIES_REV = dict((v, k) for k, v in PRIORITIES.items())


class Logger:
    """Simple logger using only syslog.

    Users of this logging object will have ``name`` prefixed to every message.

    Args:
        name: name to prefix to logging messages. The program name will be used by default.
        usestderr: Also write log messages to stderr.
        facility: name of facility. Must be one of:
                  "KERN", "USER", "MAIL", "DAEMON", "AUTH", "LPR", "NEWS", "UUCP", "CRON", "SYSLOG",
                  "LOCAL0" to "LOCAL7". Default is "USER"
        priority: name of priority level to emit log messages at. Must be one of:
                  "EMERG", "ALERT", "CRIT", "ERR", "WARNING", "NOTICE", "INFO", "DEBUG". Default is
                  "NOTICE"
    """

    _LOGGERS: Dict[str, "Logger"] = {}  # cache of all open loggers

    def __init__(self,
                 name: Optional[str] = None,
                 usestderr: Optional[bool] = False,
                 facility: Optional[str] = FACILITY,
                 priority: Optional[str] = PRIORITY):

        self.name = name or sys.argv[0].split("/")[-1]
        closelog()
        openlog(name, usestderr, facility)
        self.priority = priority

    def __del__(self):
        self.close()

    def close(self):
        try:
            del Logger._LOGGERS[self.name]
        except KeyError:
            pass
        if not Logger._LOGGERS:
            closelog()

    def debug(self, msg, *args):
        debug(f"{self.name}: {msg}", *args)

    def info(self, msg, *args):
        info(f"{self.name}: {msg}", *args)

    log = info  # backwards compatible alias

    def notice(self, msg, *args):
        notice(f"{self.name}: {msg}", *args)

    def warning(self, msg, *args):
        warning(f"{self.name}: {msg}", *args)

    def critical(self, msg, *args):
        critical(f"{self.name}: {msg}", *args)

    def fatal(self, msg, *args):
        critical(f"{self.name}: {msg}", *args)

    def alert(self, msg, *args):
        alert(f"{self.name}: {msg}", *args)

    def emergency(self, msg, *args):
        emergency(f"{self.name}: {msg}", *args)

    def syslog(self, level, msg, *args):
        syslog.syslog(level, _encode(f"{self.name}: {msg}", args))

    def exception(self, exc, *args):
        exception_error(f"{self.name}: {exc.__class__.__name__}:", exc, *args)

    def error(self, msg, *args, exc_info=None):
        if exc_info is not None:
            if exc_info is True:
                ex, val, tb = sys.exc_info()
            else:
                ex, val, tb = exc_info
            tb = None  # noqa
            exception_error(f"{self.name}: {msg}", val, *args)
        else:
            error(f"{self.name}: {msg}", *args)

    @property
    def priority(self):
        level = get_priority()
        return PRIORITIES_REV[level]

    @priority.setter
    def priority(self, newlevel):
        newlevel = PRIORITIES[newlevel.upper()]
        set_priority(newlevel)

    # Python's logging compatibility methods, note the non-PEP8 names.
    def getEffectiveLevel(self):
        return get_priority()

    def setLevel(self, newlevel):
        set_priority(newlevel)

    def addHandler(self, *args, **kwargs):
        pass  # Purposely a no-op.


class LogLevel:
    """Context manager to run a block of code at a specific log level.

    Supply the level name as a string.
    """

    def __init__(self, level):
        self._level = PRIORITIES[level.upper()]

    def __enter__(self):
        self._oldpriority = syslog.setlogmask(syslog.LOG_UPTO(self._level))

    def __exit__(self, extype, exvalue, traceback):
        syslog.setlogmask(self._oldpriority)


def get_logger(name=None, usestderr=USESTDERR, facility=FACILITY, priority=PRIORITY):
    """Get a :py:class:`Logger` object.

    May return cached logger object. Global logger configuration reflects the last one created.
    """
    name = name or os.path.basename(sys.argv[0])
    if name in Logger._LOGGERS:
        return Logger._LOGGERS[name]
    logger = Logger(name=name, usestderr=usestderr, facility=facility, priority=priority)
    Logger._LOGGERS[name] = logger
    return logger


# stock logging module compatibility objects.
# Set up custom handler for logging module that uses this module. This is for
# third-party packages that use the logging module.

# Rough guess at mapping to logging mdule levels.
_LOGGING_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.DEBUG,
    "NOTICE": logging.ERROR,
    "WARNING": logging.CRITICAL,
    "WARN": logging.CRITICAL,
    "ERR": logging.ERROR,
    "ERROR": logging.ERROR,
    "CRIT": logging.FATAL,
    "CRITICAL": logging.FATAL,
    "ALERT": logging.FATAL,
}

_LEVEL_MAP = {
    logging.CRITICAL: syslog.LOG_CRIT,
    logging.ERROR: syslog.LOG_ERR,
    logging.WARNING: syslog.LOG_WARNING,
    logging.INFO: syslog.LOG_INFO,
    logging.DEBUG: syslog.LOG_DEBUG,
}


def getLogger(name=None, *args, **kwargs):
    logging.root.info("getLogger: {}".format(name))
    return logging.root


class SyslogHandler(logging.Handler):

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        pri = PRIORITIES_REV[_LEVEL_MAP[level]]
        self._logger = Logger(usestderr=USESTDERR, priority=pri)

    def emit(self, record):
        try:
            msg = record.getMessage()
            self._logger.syslog(_LEVEL_MAP[record.levelno], msg)
        except Exception:
            self.handleError(record)


logging.root.addHandler(SyslogHandler(level=_LOGGING_LEVELS[PRIORITY]))
logging.root.level = _LOGGING_LEVELS[PRIORITY]

# Monkey patch the stock logging module to use this logger.
logging.getLogger = getLogger


def _test(argv):
    logger = Logger("testme", True)
    logger.warning("a warning")
    logger.info("some info")
    logger.notice("A notice")
    logger.debug("You don't see me")
    logger.warning("Anführungszeichen, unicode")
    logger.warning("Καλημέρα κόσμε")

    with LogLevel("DEBUG"):
        logger.info('Info with arg %s', "the arg")
        logger.debug("You see me in debug level context manager")
        logger.debug("Debug with arg: %s", "debug arg")
    logger.debug("You don't see me again")

    log = getLogger("self")
    log.warning("Test system logger warning.")
    log.error('Error message')
    try:
        raise AttributeError("bogus attr error") from KeyError("chained key error")
    except:  # noqa
        ex, val, tb = sys.exc_info()
        exception_error("testing exception_error", val)


if __name__ == "__main__":
    _test(sys.argv)
