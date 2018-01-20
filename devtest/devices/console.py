"""
Console (serial device) controller.
"""

from devtest import logging
from devtest.io import serial
from devtest.io import terminal
from devtest.io import expect
from devtest.core import exceptions


AUTOMATION_PROMPT = "OxO# "  # Simple, unique and unchanging prompt.


def get_console(ttydev, setup, account=None, password=None):
    tty = serial.SerialPort(ttydev, setup=setup)
    tty.set_min_time(4096, 50)
    term = terminal.Terminal(tty)
    if account:
        _console_login(term, account, password)
    return SerialConsole(term)


def _console_login(term, account, password):
    prompt = "root# " if account == "root" else "{}$ ".format(account)
    term.prompt = prompt
    exp = expect.Expect(term, prompt=prompt)
    exp.send("\r")
    while True:
        mo, index = exp.expect(
            ["\rlogin:", "assword:", exp.prompt, AUTOMATION_PROMPT, "\r] ",
             exp.timeoutmatch(10.0)], timeout=30.0)
        if mo:
            if index == 0:
                exp.send(account + "\r")
            elif index == 1:
                exp.send(password + "\r")
            elif index == 2:
                exp.send_slow("stty sane -echo\r")
                exp.send_slow('export PS1="{}"\r'.format(AUTOMATION_PROMPT))
                term.read_until(AUTOMATION_PROMPT.encode("ascii"))  # eat echo
                exp.send("\r")
            elif index == 3:
                exp.prompt = AUTOMATION_PROMPT
                term.prompt = AUTOMATION_PROMPT
                term.write(b"\r")
                term.flush()
                term.read_until_prompt()
                break
            elif index == 4:
                term.prompt = "] "
                logging.warning("console_login: Found recovery mode prompt.")
                break
            elif index == 5:
                raise exceptions.ControllerError("Soft timeout hit while looking for prompts.")
        else:
            raise exceptions.ControllerError("didn't match anything while logging in.")


class SerialConsole:
    def __init__(self, term):
        self._term = term

    def __repr__(self):
        return "{}({!r})".format(self.__class__.__name__, self._term)

    def close(self):
        if self._term is not None:
            self._term.close()
            self._term = None

    def fileno(self):
        return self._term.fileno()

    def write(self, data):
        return self._term.write(data)

    def read(self, amt):
        return self._term.read(amt)

    def readline(self):
        return self._term.readline()

    def send_command(self, cmd):
        # try to deal with possible console spew
        self._term.write(b"\r")
        self._term.read_until_prompt()
        # Now send the command
        self._term.write_slow(cmd.encode("ascii") + b"\r")

    def run_command(self, cmd):
        self.send_command(cmd)
        out = self._term.read_until_prompt()
        self._term.write(b"echo $?\r")
        es = self._term.read_until_prompt()
        try:
            es = int(es.strip())
        except ValueError:
            logging.warning("SerialConsole: couldn't get exit status.")
            es = -1
        return es, out


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
