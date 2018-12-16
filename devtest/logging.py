"""
Replacement logging module. This module is light, and intended to leverage the
sytem's syslog service. Log destination configuration should be done there.

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

DEVTEST_LOG_LEVEL
    Sets the syslog level to log, default NOTICE.

DEVTEST_LOG_STDERR
    Set to include stderr in log output.

You may use a function call interface, with the various logging functions, or
the object interface by getting a Logger instance.

View log output in a shell like this:

    # log stream --predicate 'senderImagePath contains "Python"' --level debug
"""


import sys
import os
import syslog


# also import and configure standard logging here. Avoid using the logging
# module in other code.
import logging

FACILITY = os.environ.get("DEVTEST_LOG_FACILITY", "USER")
LEVEL = os.environ.get("DEVTEST_LOG_LEVEL", "NOTICE")
USESTDERR = bool(os.environ.get("DEVTEST_LOG_STDERR"))


_oldloglevel = syslog.setlogmask(syslog.LOG_UPTO(
    getattr(syslog, "LOG_" + LEVEL)))


def DEBUG(*args, **kwargs):
    """Use this instead of 'print()' when debugging. Prints to stderr.
    """
    parts = []
    for name, value in list(kwargs.items()):
        parts.append("{}: {!r}".format(name, value))
    print("DEBUG", " ".join(str(o) for o in args), ", ".join(parts),
          file=sys.stderr)


def openlog(ident=None, usestderr=USESTDERR, facility=FACILITY):
    opts = syslog.LOG_PID | syslog.LOG_PERROR if usestderr else 0
    if isinstance(facility, str):
        facility = getattr(syslog, "LOG_" + facility)
    if ident is None:  # openlog does not take None as an ident parameter.
        syslog.openlog(logoption=opts, facility=facility)
    else:
        syslog.openlog(ident=ident, logoption=opts, facility=facility)


def close():
    syslog.closelog()


def debug(msg):
    syslog.syslog(syslog.LOG_DEBUG, _encode(msg))


def info(msg):
    syslog.syslog(syslog.LOG_INFO, _encode(msg))


def notice(msg):
    syslog.syslog(syslog.LOG_NOTICE, _encode(msg))


def warning(msg):
    syslog.syslog(syslog.LOG_WARNING, _encode(msg))


def error(msg):
    syslog.syslog(syslog.LOG_ERR, _encode(msg))


def critical(msg):
    syslog.syslog(syslog.LOG_CRIT, _encode(msg))


def alert(msg):
    syslog.syslog(syslog.LOG_ALERT, _encode(msg))


def emergency(msg):
    syslog.syslog(syslog.LOG_EMERG, _encode(msg))


def _encode(o):
    # Causes UTF8 BOM to be added to message per RFC-5424
    return '\ufeff' + str(o).replace("\r\n", " ")


# set loglevels
def get_logmask():
    return syslog.setlogmask(0)


def loglevel(level):
    global _oldloglevel
    _oldloglevel = syslog.setlogmask(syslog.LOG_UPTO(level))


def get_loglevel():
    mask = syslog.setlogmask(0)
    for level in (syslog.LOG_DEBUG, syslog.LOG_INFO, syslog.LOG_NOTICE,
                  syslog.LOG_WARNING, syslog.LOG_ERR, syslog.LOG_CRIT,
                  syslog.LOG_ALERT, syslog.LOG_EMERG):
        if syslog.LOG_MASK(level) & mask:
            return level


def loglevel_restore():
    syslog.setlogmask(_oldloglevel)


def loglevel_debug():
    loglevel(syslog.LOG_DEBUG)


def loglevel_info():
    loglevel(syslog.LOG_INFO)


def loglevel_notice():
    loglevel(syslog.LOG_NOTICE)


def loglevel_warning():
    loglevel(syslog.LOG_WARNING)


def loglevel_error():
    loglevel(syslog.LOG_ERR)


def loglevel_critical():
    loglevel(syslog.LOG_CRIT)


def loglevel_alert():
    loglevel(syslog.LOG_ALERT)


# common logging patterns
def exception_error(prefix, ex):
    error("{}: {}".format(prefix, _format_exception(ex)))


def exception_warning(prefix, ex):
    warning("{}: {}".format(prefix, _format_exception(ex)))


def _format_exception(ex):
    s = ["{} ({})".format(ex.__class__.__name__, ex)]
    orig = ex
    while ex.__context__ is not None:
        ex = ex.__context__
        s.append(" Within: {} ({})".format(ex.__class__.__name__, ex))
    ex = orig
    while ex.__cause__ is not None:
        ex = ex.__cause__
        s.append(" From: {} ({})".format(ex.__class__.__name__, ex))
    return " | ".join(s)


# Allow use of names, and useful aliases, to select logging level.
LEVELS = {
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
LEVELS_REV = dict((v, k) for k, v in list(LEVELS.items()))

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


class Logger:
    """Simple logger using only syslog."""
    def __init__(self, name=None, usestderr=False, facility=FACILITY,
                 level=LEVEL):
        self.name = name or sys.argv[0].split("/")[-1]
        close()
        openlog(name, usestderr, facility)
        self.loglevel = level

    def close(self):
        close()

    def debug(self, msg):
        debug(msg)

    def info(self, msg):
        info(msg)
    log = info

    def notice(self, msg):
        notice(msg)

    def warning(self, msg):
        warning(msg)

    def critical(self, msg):
        critical(msg)

    def fatal(self, msg):
        critical(msg)

    def alert(self, msg):
        alert(msg)

    def emergency(self, msg):
        emergency(msg)

    def syslog(self, level, msg):
        syslog.syslog(level, _encode(msg))

    def exception(self, ex, val, tb=None):
        error("Exception: {}: {}".format(ex.__name__, val))

    def error(self, msg, exc_info=None):
        if exc_info is not None:
            if exc_info is True:
                ex, val, tb = sys.exc_info()
            else:
                ex, val, tb = exc_info
            tb = None  # noqa
            msg = "{}: {} ({})".format(msg, ex.__name__, val)
        error(msg)

    @property
    def logmask(self):
        return syslog.setlogmask(0)

    @logmask.setter
    def logmask(self, newmask):
        syslog.setlogmask(newmask)

    @property
    def loglevel(self):
        level = get_loglevel()
        return LEVELS_REV[level]

    @loglevel.setter
    def loglevel(self, newlevel):
        newlevel = LEVELS[newlevel.upper()]
        loglevel(newlevel)

    # Python's logging compatibility methods, note the non-PEP8 names.
    def getEffectiveLevel(self):
        return get_loglevel()

    def setLevel(self, newlevel):
        loglevel(newlevel)

    def addHandler(self, *args, **kwargs):
        pass


class LogLevel:
    """Context manager to run a block of code at a specific log level.

    Supply the level name as a string.
    """
    def __init__(self, level):
        self._level = LEVELS[level.upper()]

    def __enter__(self):
        self._oldloglevel = syslog.setlogmask(syslog.LOG_UPTO(self._level))

    def __exit__(self, extype, exvalue, traceback):
        syslog.setlogmask(self._oldloglevel)


# Set up custom handler for logging module that uses this module. This is for
# third-party packages that use the logging module.

_LOGGERS = {}


def get_logger(*args, **kwargs):
    name = args[0] if len(args) > 1 else "root"
    if name in _LOGGERS:
        return _LOGGERS[name]
    facility = kwargs.get("facility", FACILITY)
    level = kwargs.get("level", LEVEL)
    _logger = Logger(name, facility=facility, level=level)
    _LOGGERS[name] = _logger
    return _logger


def getLogger(name=None, *args, **kwargs):
    logging.root.info("getLogger: {}".format(name))
    return logging.root


class SyslogHandler(logging.Handler):

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._logger = get_logger()

    def emit(self, record):
        try:
            msg = record.getMessage()
            self._logger.syslog(_LEVEL_MAP[record.levelno], msg)
        except Exception:
            self.handleError(record)


logging.root.addHandler(SyslogHandler())
logging.root.level = _LOGGING_LEVELS[LEVEL]


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
        logger.debug("You see me in debug level context manager")
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

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
