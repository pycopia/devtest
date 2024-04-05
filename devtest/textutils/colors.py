"""Support colorizing text in terminals.
"""

__all__ = [
    'color', 'red', 'green', 'blue', 'cyan', 'magenta', 'yellow', 'white', 'underline', 'inverse',
    'box'
]

from functools import partial

RESET = NORMAL = "\x1b[0m"

ITALIC_ON = "\x1b[3m"
ITALIC_OFF = "\x1b[23m"

UNDERLINE_ON = "\x1b[4m"
UNDERLINE_OFF = "\x1b[24m"

INVERSE_ON = "\x1b[7m"
INVERSE_OFF = "\x1b[27m"

RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
GREY = "\x1b[37m"

LT_RED = "\x1b[31:01m"
LT_GREEN = "\x1b[32:01m"
LT_YELLOW = "\x1b[33;01m"
LT_BLUE = "\x1b[34;01m"
LT_MAGENTA = "\x1b[35;01m"
LT_CYAN = "\x1b[36;01m"
WHITE = BRIGHT = "\x1b[01m"

RED_BACK = "\x1b[41m"
GREEN_BACK = "\x1b[42m"
YELLOW_BACK = "\x1b[43m"
BLUE_BACK = "\x1b[44m"
MAGENTA_BACK = "\x1b[45m"
CYAN_BACK = "\x1b[46m"
WHITE_BACK = "\x1b[47m"

_FG_MAP = {
    "red": RED,
    "green": GREEN,
    "yellow": YELLOW,
    "blue": BLUE,
    "magenta": MAGENTA,
    "cyan": CYAN,
    "grey": GREY,
    "gray": GREY,
    "white": BRIGHT,
}

_LT_FG_MAP = {
    "red": LT_RED,
    "green": LT_GREEN,
    "yellow": LT_YELLOW,
    "blue": LT_BLUE,
    "magenta": LT_MAGENTA,
    "cyan": LT_CYAN,
    "white": BRIGHT,
}

_BG_MAP = {
    "red": RED_BACK,
    "green": GREEN_BACK,
    "yellow": YELLOW_BACK,
    "blue": BLUE_BACK,
    "magenta": MAGENTA_BACK,
    "cyan": CYAN_BACK,
    "white": WHITE_BACK,
    None: "",
}

#                 UL  hor   vert  UR  LL   LR
_BOXCHARS = {
    0: ['┏', '━', '┃', '┓', '┗', '┛'],
    1: ['╔', '═', '║', '╗', '╚', '╝'],
    2: ['┌', '─', '│', '┐', '└', '┘']
}


def color(text, fg, bg=None, bold=False):
    """Return a new text string with color codes added.
    """
    try:
        c = _LT_FG_MAP[fg] if bold else _FG_MAP[fg]
        return c + _BG_MAP[bg] + text + RESET
    except KeyError:
        raise ValueError("Bad color value: {},{}".format(fg, bg))


# These are the primary functions you would call.
red = partial(color, fg="red")
green = partial(color, fg="green")
blue = partial(color, fg="blue")
cyan = partial(color, fg="cyan")
magenta = partial(color, fg="magenta")
yellow = partial(color, fg="yellow")
white = partial(color, fg="white")


def underline(text):
    return UNDERLINE_ON + text + UNDERLINE_OFF


def inverse(text):
    return INVERSE_ON + text + INVERSE_OFF


def box(text, level=0, color=GREY):
    """Draw a unicide box-drawing character box with text in it.
    """
    UL, hor, vert, UR, LL, LR = _BOXCHARS[level]
    tt = "{}{}{}".format(UL, hor * (len(text) + 2), UR)
    bt = "{}{}{}".format(LL, hor * (len(text) + 2), LR)
    ml = "{} {}{}{} {}".format(vert, color, text, RESET, vert)
    return "\n".join((tt, ml, bt))


def _test(argv):
    print(box("Test me"))
    print(box("Test me", 1, color=YELLOW))
    print(box("Test me", 2, color=RED))

    print(green("Green"))
    print(green("Green on Red", bg="red"))
    print(red("This sentence is red, except for " + green("these words, which are green") + "."))
    print(cyan("Cyan"), cyan("Bright Cyan", bold=True))
    print("Regular", white("and white"))


if __name__ == "__main__":
    import sys
    _test(sys.argv)
