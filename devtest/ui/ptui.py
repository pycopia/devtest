"""Not-so-simple UI built on the prompt-toolkit framework.
"""

import inspect
from textwrap import dedent

from pygments.styles.vim import VimStyle as DevtestStyle
from pygments.lexers import markup
from pygments.formatters import terminal
from pygments import highlight

from prompt_toolkit import PromptSession
from prompt_toolkit import output
from prompt_toolkit import input as ptinput
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout, VSplit
from prompt_toolkit.styles import style_from_pygments_cls
from prompt_toolkit.widgets import (
    Button,
    CheckboxList,
    Dialog,
    Label,
    RadioList,
)

STYLE = style_from_pygments_cls(DevtestStyle)

bindings = KeyBindings()
bindings.add("tab")(focus_next)
bindings.add("right")(focus_next)
bindings.add("s-tab")(focus_previous)
bindings.add("left")(focus_previous)


@bindings.add("c-c")
def app_exit(event):
    get_app().exit()


KEYBINDINGS = merge_key_bindings([load_key_bindings(), bindings])
del bindings


class PromptToolkitUserInterface:

    def __init__(self):
        self._output = output.create_output()
        self._input = ptinput.create_input(always_prefer_tty=True)
        self._ps = PromptSession(input=self._input, output=self._output, style=STYLE)
        self._doclexer = markup.RstLexer()
        self._formatter = terminal.TerminalFormatter()

    def print(self, *args):
        print(*args, file=self._output.stdout)

    def write(self, data):
        self._output.stdout.write(data)

    def display(self, text):
        self.print(dedent(text))

    def write_doc(self, docstring):
        doc = inspect.cleandoc(docstring)
        self._output.stdout.write(highlight(doc, self._doclexer, self._formatter))
        self._output.stdout.write("\n")
        self._output.stdout.flush()

    def user_input(self, prompt="", multiline=False):
        return self._ps.prompt([("bold", prompt)], multiline=multiline)

    def yes_no(self, prompt, default=True):
        result = bool(default)

        def yes_handler(evt=None) -> None:
            nonlocal result
            result = True
            get_app().exit()

        def no_handler(evt=None) -> None:
            nonlocal result
            result = False
            get_app().exit()

        keybindings = KeyBindings()
        keybindings.add("y")(yes_handler)
        keybindings.add("n")(no_handler)

        dialog = VSplit(children=[
            Label([("bold", prompt)], dont_extend_width=True),
            Button(text="Yes", width=8, handler=yes_handler),
            Button(text="No", width=8, handler=no_handler)
        ],
                        padding=1,
                        padding_char=" ")
        app = Application(
            layout=Layout(dialog, focused_element=dialog.children[1 if result else 2]),
            key_bindings=merge_key_bindings([KEYBINDINGS, keybindings]),
            mouse_support=True,
            style=STYLE,
            full_screen=False,
        )
        app.run()
        return result

    def choose(self, somelist, defidx=0, prompt="Choose from list", display_filter=str):

        selections = RadioList(values=[(el, display_filter(el)) for el in somelist])

        def cancel_handler() -> None:
            get_app().exit()

        def ok_handler():
            get_app().exit(result=selections.current_value)

        dialog = Dialog(title=prompt,
                        body=selections,
                        buttons=[
                            Button(text="OK", handler=ok_handler),
                            Button(text="Cancel", handler=cancel_handler)
                        ],
                        with_background=True)

        app = Application(
            layout=Layout(dialog),
            key_bindings=KEYBINDINGS,
            mouse_support=True,
            style=STYLE,
            full_screen=True,
        )
        return app.run()

    def choose_multiple(self, choices, prompt="choose"):
        keybindings = KeyBindings()

        selections = CheckboxList(values=choices)

        def cancel_handler() -> None:
            get_app().exit()

        def ok_handler():
            get_app().exit(result=selections.current_values)

        dialog = Dialog(title=prompt,
                        body=selections,
                        buttons=[
                            Button(text="Done", handler=ok_handler),
                            Button(text="Cancel", handler=cancel_handler)
                        ],
                        with_background=True)

        app = Application(layout=Layout(dialog),
                          key_bindings=merge_key_bindings([KEYBINDINGS, keybindings]),
                          mouse_support=True,
                          style=STYLE,
                          full_screen=True)
        return app.run()


if __name__ == "__main__":
    ui = PromptToolkitUserInterface()
    ui.write("Self testing.\n")
    print(ui.user_input("Type something:"))
    ui.print("Alt-Enter to exit.")
    print(ui.user_input("Type some lines:", multiline=True))
    print(ui.yes_no("Did it Pass?", default=False))
    print(ui.choose(["one", "two", "three"], prompt="Which number?"))
    choices = [
        ("one", [("fg:ansiyellow", "one")]),
        ("two", [("fg:green", "two")]),
        ("three", [("fg:red", "three")]),
    ]
    print(ui.choose_multiple(choices, prompt="Which numbers?"))
