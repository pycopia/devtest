"""Simple UI for interacting with user from shell.
"""

import sys
import os
import curses
import curses.ascii
import curses.textpad

# keep this import. It works around some strange Python behavior.
# Without it, the built-in function "input" writes prompt to stderr.
# With this imported, the "input" function writes prompt to stdout (as it
# should).
import readline  # noqa

try:
    COLUMNS, LINES = os.get_terminal_size()
except OSError:
    COLUMNS, LINES = 80, 24


class ConsoleIO:

    def __init__(self):
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.mode = "w"
        self.closed = 0
        self.softspace = 0
        # reading methods
        self.read = self.stdin.read
        self.readline = self.stdin.readline
        self.readlines = self.stdin.readlines
        # writing methods
        self.write = self.stdout.write
        self.flush = self.stdout.flush
        self.writelines = self.stdout.writelines

    def input(self, prompt=""):
        return input(prompt)

    def close(self):
        self.stdout = None
        self.stdin = None
        self.closed = 1
        del self.read, self.readlines, self.write
        del self.flush, self.writelines


def get_input(prompt="", default=None, input=input):
    """Get user input with an optional default value."""
    if default is not None:
        ri = input("%s [%s]> " % (prompt, default))
        if not ri:
            return default
        else:
            return ri
    else:
        return input("%s> " % (prompt,))


def choose(somelist, defidx=0, prompt="choose", lines=LINES, columns=COLUMNS):
    """Simple interactive chooser.

    Choose an item from a list.
    """
    return curses.wrapper(_choose, somelist, defidx, prompt, lines, columns)


def _choose(stdscr, somelist, defidx, prompt, lines, columns):
    oldcur = curses.curs_set(0)
    pad = curses.newpad(len(somelist) + 1, columns - 2)
    for line in somelist:
        pad.addstr(str(line) + "\n")
    pminrow = defidx  # also somelist index
    pmincol = 0
    sminrow = 2
    smincol = 1
    smaxrow = lines - 3
    smaxcol = columns - 2

    # Build form
    stdscr.clear()
    stdscr.addstr("{} (Press Enter to select)".format(prompt))
    curses.textpad.rectangle(stdscr, 1, 0, lines - 2, columns - 1)
    stdscr.refresh()
    pad.chgat(pminrow, 0, smaxcol - 1, curses.A_REVERSE)
    pad.refresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
    J, K = [b'jk'[i] for i in range(2)]
    esc = False
    while 1:
        ch = stdscr.getch()
        if ch in (curses.KEY_DOWN, J):
            pminrow = min(len(somelist) - 1, max(0, pminrow + 1))
        elif ch in (curses.KEY_UP, K):
            pminrow = max(0, min(len(somelist), pminrow - 1))
        elif ch == curses.ascii.NL:
            break
        elif ch == curses.ascii.ESC:
            esc = True
            break

        pad.chgat(pminrow + 1, 0, smaxcol - 1, curses.A_NORMAL)
        pad.chgat(pminrow, 0, smaxcol - 1, curses.A_REVERSE)
        pad.noutrefresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
        curses.doupdate()

    curses.curs_set(oldcur)
    if esc:
        return None
    else:
        return somelist[pminrow]


def choose_multiple(somelist, prompt="choose", lines=LINES, columns=COLUMNS):
    """Simple interactive chooser of multiple items.

    Choose several items from a list.

    Returns:
        List of chosen objects.
    """
    return curses.wrapper(_choose_multiple, somelist, prompt, lines, columns)


def _choose_multiple(stdscr, somelist, prompt, lines, columns):
    selected = []
    oldcur = curses.curs_set(0)

    pad = curses.newpad(len(somelist) + 1, columns - 2)
    for line in somelist:
        pad.addstr(str(line) + "\n")
    pminrow = 0
    pmincol = 0
    sminrow = 2
    smincol = 1
    smaxrow = lines - 3
    smaxcol = columns - 2

    # Build form
    stdscr.clear()
    stdscr.addstr(f"{prompt} (Press Enter to select, q exits)")
    curses.textpad.rectangle(stdscr, 1, 0, lines - 2, columns - 1)
    stdscr.refresh()
    pad.chgat(pminrow, 0, smaxcol - 1, curses.A_REVERSE)
    pad.refresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
    # Vi-like keyboard control
    J, K, Q = b'jkq'

    esc = False
    while 1:
        ch = stdscr.getch()
        if ch in (curses.KEY_DOWN, J):
            pminrow = min(len(somelist) - 1, max(0, pminrow + 1))
        elif ch in (curses.KEY_UP, K):
            pminrow = max(0, min(len(somelist), pminrow - 1))
        elif ch == curses.ascii.NL:
            selected.append(somelist[pminrow])
            pad.chgat(pminrow, 0, smaxcol - 1, curses.A_REVERSE)
        elif ch == Q:
            break
        elif ch == curses.ascii.ESC:
            esc = True
            break

        pad.chgat(pminrow + 1, 0, smaxcol - 1, curses.A_NORMAL)
        pad.chgat(pminrow, 0, smaxcol - 1, curses.A_REVERSE)
        pad.noutrefresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
        curses.doupdate()

    curses.curs_set(oldcur)
    if esc:
        return None
    else:
        return selected


def get_text(title=None):
    return curses.wrapper(_get_text, title)


def _get_text(stdscr, title):
    tb = curses.textpad.Textbox(stdscr)
    tb.stripspaces = True
    return tb.edit()


class SimpleUserInterface:

    def __init__(self, io=None):
        self._io = io or ConsoleIO()

    def __del__(self):
        self._io.close()
        self._io = None

    def print(self, *args):
        print(*args, file=self._io.stdout)

    def write(self, data):
        self._io.write(data)

    def user_input(self, prompt=None):
        return self._io.input(prompt)

    def yes_no(self, prompt, default=True):
        while 1:
            yesno = get_input(prompt, "Y" if default else "N", self._io.input)
            yesno = yesno.upper()
            if yesno.startswith("Y"):
                return True
            elif yesno.startswith("N"):
                return False
            else:
                self.print("Please enter yes or no.")

    def choose(self, somelist, defidx=0, prompt="choose"):
        return choose(somelist, defidx=defidx, prompt=prompt)

    def choose_multiple(self, somelist, prompt="choose"):
        return choose_multiple(somelist, prompt=prompt)


if __name__ == "__main__":
    ui = SimpleUserInterface()
    with open("/etc/protocols") as fo:
        lines = [line.strip() for line in fo.readlines()]
    print(ui.choose(lines, defidx=3, prompt="Pick a service"))
    print(ui.yes_no("Y or N?"))
    print("Enter some text, Ctl-G when done.")
    print(get_text("test me"))
    print(ui.choose_multiple(lines, prompt="Pick services"))
