"""A terminal based user interface for the database.
"""

import sys
import os
import time
import textwrap
from html.parser import HTMLParser

from devtest.textutils import colors
from devtest.db import controllers

if os.isatty(sys.stdout.fileno()):
    WIDTH = os.get_terminal_size()[0] - 16
else:
    WIDTH = 80

_deep_text_wrapper = textwrap.TextWrapper(width=WIDTH,
                                          initial_indent=" " * 21,
                                          subsequent_indent=" " * 21)

_medium_text_wrapper = textwrap.TextWrapper(width=WIDTH,
                                            initial_indent=" " * 10,
                                            subsequent_indent=" " * 10)

_shallow_text_wrapper = textwrap.TextWrapper(width=WIDTH,
                                             initial_indent=" " * 4,
                                             subsequent_indent=" " * 4)

_LEVELS = {
    1: _shallow_text_wrapper,
    2: _medium_text_wrapper,
    3: _deep_text_wrapper,
}


def print_nested(obj, level=0, color=None):
    """Fancier print function that can indent and colorize.
    """
    if color is not None:
        colorf = getattr(colors, color, None)
        if colorf is None:
            raise ValueError("Invalid color name: {color}")
        obj = colorf(str(obj))
    if level == 0:
        print(obj)
        return
    wrapper = _LEVELS.get(level)
    if wrapper is None:
        raise ValueError(f"print level must be 0, 1, 2, or 3, not {level}.")
    print(wrapper.fill(str(obj)))


def list_functions(like, verbose):
    for func in controllers.FunctionController.all(like):
        show_function(func, verbose)


def show_function(func, verbose):
    print(colors.green(func.name))
    if verbose:
        if func.description:
            print(_shallow_text_wrapper.fill(func.description))
        if func.implementation:
            print("    Implemented by:", colors.underline(func.implementation))


def list_accounts(like, verbose):
    for acc in controllers.AccountIdsController.all(like):
        show_account(acc, verbose)


def show_account(acc, verbose):
    if acc.admin:
        colorf = colors.green
    else:
        colorf = colors.yellow
    print(colorf(acc.identifier), "(admin)" if acc.admin else "")
    if verbose:
        if acc.note:
            print(_shallow_text_wrapper.fill(acc.note))
        if acc.login:
            print("       login:", acc.login)
        if acc.password:
            print("    password:", colors.red(acc.password))
        if acc.private_key:
            print("    has private key.")
        if acc.public_key:
            print("    has public key, or certificate.")
            print(bytes(acc.public_key).decode("ascii"))


def list_testbeds(like, verbose):
    for tb in controllers.TestBedController.all(like):
        print(colors.green(tb.name))
        if verbose:
            show_testbed_object(tb)


def show_testbed(name, verbose=False):
    tb = controllers.TestBedController.get(name)
    if tb:
        print(colors.green(tb.name))
        if tb.notes:
            print(_shallow_text_wrapper.fill(tb.notes))
        show_attributes(tb.attributes, indent=2)
        print("  Test equipment:")
        show_testbed_object(tb, verbose)
    else:
        print(tb)


def show_testbed_object(tb, verbose=False):
    for te in tb.testequipment:
        if verbose:
            eq = te.equipment
            status = "" if eq.active else "(inactive)"
            role = te.function.name
            print("\n   ", colors.magenta(eq.model.name), colors.white(eq.name, bold=True),
                  eq.serno, status, "role:", role)
            if eq.notes:
                print(_medium_text_wrapper.fill(eq.notes))
            if eq.partof:
                print("    ", colors.cyan("Part of:"), eq.partof)
            print("    ", colors.cyan("Location:"), eq.location)
            if eq.account:
                print("    ", colors.cyan("Accessor account:"), eq.account)
            if eq.user:
                print("    ", colors.cyan("    User account:"), eq.user)
            show_attributes(eq.attributes, indent=4)
            if eq.interfaces:
                print("    ", colors.cyan("Network interfaces:"))
                for iface in eq.interfaces:
                    print("       ", iface)
        else:
            print("   ", te.equipment.name, "role:", te.function.name)


def list_equipmentmodels(like, verbose):
    for eqm in controllers.EquipmentModelController.all(like):
        print("{:>20.20s} {}".format(eqm.manufacturer, colors.white(eqm.name, bold=True)))
        if verbose:
            if eqm.note:
                print(" " * 20, eqm.note)
            if eqm.specs:
                print(colors.cyan("                     Specs:"), eqm.specs)
            if eqm.attributes:
                print(
                    _deep_text_wrapper.fill(", ".join(
                        "{}={!r}".format(k, v) for k, v in eqm.attributes.items())))


def show_equipmentmodel(name, manufacturer=None, verbose=False):
    eqm = controllers.EquipmentModelController.get(name, manufacturer)
    if eqm:
        print(eqm.manufacturer, colors.white(eqm.name, bold=True))
        if eqm.note:
            print(_shallow_text_wrapper.fill(eqm.note))
        if eqm.specs:
            print(colors.cyan("  Specs:"), eqm.specs)
        if verbose:
            show_attributes(eqm.attributes)
    else:
        print(eqm)


def show_attributes(attributes, indent=4):
    if attributes:
        print(" " * indent, colors.cyan("Attributes:"))
        for key, value in attributes.items():
            if "passw" in key or "secret" in key or "private" in key:
                value = "<ELIDED>"
            print("{}{:>25.25s}={!r}".format(" " * indent, key, value))


def show_equipment(name, verbose=False):
    eq = controllers.EquipmentController.get(name)
    if eq:
        _show_equipment(eq, verbose)
    else:
        print(eq)


def _show_equipment(eq, verbose):
    status = "" if eq.active else "(inactive)"
    print(colors.magenta(eq.model.name), colors.white(eq.name, bold=True), eq.serno, status)
    if eq.notes:
        print(_shallow_text_wrapper.fill(eq.notes))
    if eq.partof:
        print(colors.cyan("  Part of:"), eq.partof)
    print(colors.cyan("  Location:"), eq.location)
    if eq.account:
        print(colors.cyan("  Accessor account:"), eq.account)
    if eq.user:
        print(colors.cyan("      User account:"), eq.user)
    show_attributes(eq.attributes)
    if eq.interfaces:
        print(colors.cyan("  Network interfaces:"))
        for iface in eq.interfaces:
            print("    ", iface, "=>", iface.network)
    if eq.connections:
        print(colors.cyan("  Connections:"))
        for connection in eq.connections:
            print("    ", connection)
    if verbose:
        print(colors.cyan("  Subequipment:"))
        for subeq in eq.subcomponents:
            _show_equipment(subeq, False)
            print()


def list_equipment(like, verbose):
    for eq in controllers.EquipmentController.all(like):
        if verbose:
            _show_equipment(eq, verbose)
            print()
        else:
            print("{:>30.30s} {}".format(eq.model.name, colors.white(eq.name, bold=True)))


def list_networks(like, verbose):
    for nw in controllers.NetworksController.all(like):
        print(colors.white(nw.name, bold=True))
        if verbose:
            if nw.attributes:
                print(
                    _deep_text_wrapper.fill(", ".join(
                        "{}={!r}".format(k, v) for k, v in nw.attributes.items())))


def show_network(nw, verbose):
    if nw.layer == 2 and nw.vlanid is not None:
        print(colors.white(nw.name, bold=True), "vlan: {} type: {!s}".format(nw.vlanid, nw.type))
    elif nw.layer == 3:
        print(colors.white(nw.name, bold=True),
              "ip4: {}, ip6: {}, type: {!s}".format(nw.ipnetwork, nw.ip6network, nw.type))
    else:
        print(colors.white(nw.name, bold=True), "layer: {}, type: {!s}".format(nw.layer, nw.type))
    if verbose:
        if nw.notes:
            print(colors.cyan("  Notes:"))
            print(_shallow_text_wrapper.fill(nw.notes))
        if nw.attributes:
            print(
                _deep_text_wrapper.fill(", ".join(
                    "{}={!r}".format(k, v) for k, v in nw.attributes.items())))
        if nw.lower:
            print(colors.cyan("  Lower Layer:"))
            show_network(nw.lower, verbose)
        if nw.upper:
            print(colors.cyan("  Upper Layer:"))
            show_network(nw.upper, verbose)
        print(colors.magenta("  Attached interfaces:"))
        for iface in nw.interfaces:
            print("    ", iface.equipment.name, iface.name)


def show_scenario(scenario):
    print(colors.box(scenario.name))
    if scenario.purpose:
        print(colors.cyan("  Purpose:"))
        parser = TCParser()
        parser.feed(scenario.purpose)
        parser.close()
    if scenario.notes:
        print(colors.cyan("  Notes:"))
        print(_shallow_text_wrapper.fill(scenario.notes))
    print(colors.cyan("    Implementation:"), scenario.implementation)
    print(colors.cyan("        Parameters:"), scenario.parameters)
    print(colors.cyan("       Report Name:"), scenario.reportname)
    # scenario.owners         #  ArrayField(null=True)  # Array of employee IDs
    if scenario.testbed:
        print(colors.cyan("           TestBed:"), scenario.testbed.name)
    if scenario.testsuite:
        print(colors.cyan("         TestSuite:"), scenario.testsuite.name)


def show_testsuite(suite):
    COL = colors.CYAN if suite.valid else colors.RED
    print(colors.box(suite.name, level=1, color=COL))
    if suite.purpose:
        print(colors.cyan("  Purpose:"))
        parser = TCParser()
        parser.feed(suite.purpose)
        parser.close()
    print(colors.cyan("    Implementation:"), suite.suiteimplementation)
    print(colors.cyan("      Last Changed:"), suite.lastchange)
    if suite.test_cases:  # Ordered array of TestCase.id values.
        for tc in suite.test_cases:
            print(tc)
    # owners = ArrayField(null=True)  # Array of employee IDs


def show_testcase(testcase):
    parser = TCParser()
    COL = colors.GREEN if testcase.valid else colors.RED
    print(colors.box(testcase.name, level=2, color=COL))
    print("   ", _TESTCASE_TYPES[(testcase.interactive, testcase.automated)])
    print(colors.cyan("    Implementation:"), testcase.testimplementation)
    print(colors.cyan("              Type:"), testcase.type)
    print(colors.cyan("          Priority:"), testcase.priority)
    print(colors.cyan("            Status:"), testcase.status)
    print(colors.cyan("      Last Changed:"), testcase.lastchange)
    if testcase.attributes:
        print(colors.cyan("        Attributes:"), testcase.attributes)
    if testcase.comments:
        print(colors.cyan("    Comments:"))
        print(_shallow_text_wrapper.fill(testcase.comments))
    for attrname in ("purpose", "passcriteria", "startcondition", "endcondition", "procedure"):
        value = getattr(testcase, attrname)
        if value:
            parser.reset()
            parser.feed(value)
            parser.close()


# (interactive, automated) | meaning
_TESTCASE_TYPES = {
    (False, False):
        "A manual test; the user must supply final result.",
    (False, True):
        "A fully automated test.",
    (True, False):
        "A manual test; the user must supply final result and data.",
    (True, True): ("A partially automated test; "
                   "needs user input but result is automatically reported."),
}


# For now, testcases keep text fields in HTML markup. Might change later.
# Just use this simple HTML formatter for now.
class TCParser(HTMLParser):

    def reset(self):
        super().reset()
        self._stack = []
        self._state = 0
        self._count = 0
        self._indent = self._initial_indent = 8
        self._current_tag = ""

    def close(self):
        super().close()
        self._stack.append("\n")
        for el in self._stack:
            sys.stdout.write(el)

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self._stack.append(colors.CYAN)
            self._indent += 4
        elif tag == "ol":
            self._indent = 8
            self._count = 1
        elif tag == "ul":
            self._indent = 8
            self._count = 0
        elif tag == "li":
            if self._count > 0:
                self._stack.append(" " * self._indent + "{}. ".format(self._count))
                self._count += 1
            else:
                self._stack.append(" " * self._indent + "* ")
            self._initial_indent = 0
        elif tag == "cite":
            self._stack.append(" ")
            self._stack.append(colors.UNDERLINE_ON)
        elif tag == "strong":
            self._stack.append(" ")
            self._stack.append(colors.BRIGHT)
        elif tag == "p":
            self._stack.append("")
        self._current_tag = tag

    def handle_endtag(self, tag):
        if tag == "h1":
            self._stack.append(colors.RESET)
            self._stack.append("\n")
        elif tag == "ol":
            self._indent -= 4
            self._initial_indent = 4
            self._count = 0
        elif tag == "ul":
            self._indent -= 4
            self._initial_indent = 4
        elif tag == "cite":
            self._stack.append(colors.UNDERLINE_OFF)
            self._stack.append(" ")
        elif tag == "strong":
            self._stack.append(colors.RESET)
            self._stack.append(" ")
        elif tag == "p":
            self._stack.append("\n")
        else:
            self._stack.append("\n")

    def handle_data(self, text):
        text = text.strip()
        if not text:
            return
        text = text.replace("\n", " ")
        if self._current_tag == "h1":
            self._stack.append("    " + text + ":")
        elif self._current_tag == "cite":
            self._stack.append(text)
        elif self._current_tag == "strong":
            self._stack.append(text)
        elif self._current_tag == "li":
            self._stack.append(
                textwrap.fill(text,
                              width=WIDTH - self._indent,
                              initial_indent="",
                              subsequent_indent=" "))
        elif self._current_tag == "p":
            self._stack.append(text)
        else:
            self._stack.append(
                textwrap.fill(text,
                              width=WIDTH - self._indent,
                              initial_indent=" " * self._indent,
                              subsequent_indent=" " * self._indent))


def show_testresult(result, failures=False, summarize=False, testcase_name=None):
    if result.resulttype == controllers.TestResultsController.RESULT_TYPE_MAP["summary"]:
        print(colors.white("Test Run\n========"))
        print("  Id: {}, Testbed: {}".format(result.id, result.testbed))
        if result.dutbuild:
            print("  DUT build:", result.dutbuild)
        print("  Artifact location:", result.resultslocation)
        if result.arguments:
            print("Arguments:", result.arguments)
        if result.note:
            print("  NOTE:", result.note)
        for result in controllers.TestResultsController.subresults(result, failures=failures):
            _print_result_other(result, 0, failures, summarize)
        print()
    elif result.resulttype == controllers.TestResultsController.RESULT_TYPE_MAP["suite"]:
        _print_suite_result(result, 0, failures, summarize)
    elif result.resulttype == controllers.TestResultsController.RESULT_TYPE_MAP["test"]:
        _print_testcase_result(result, 0, summarize, testcase_name)


def show_run_result(result, summarize=False):
    if summarize:
        suitetype = controllers.TestResultsController.RESULT_TYPE_MAP["suite"]
        srs = []
        for sr in result.subresults:
            if sr.resulttype == suitetype:
                srs.append(f"{sr.testsuite.name} {sr.result}")
        print(f"Run: {result.id:4d} started: {result.starttime} {' '.join(srs)}")
        return
    print(colors.white("Test Run\n========"))
    print("    Started:", result.starttime)
    print("      Ended:", result.endtime)
    if result.endtime:
        print("  Elapsed:", result.endtime - result.starttime)
    print("  Testbed: {}".format(result.testbed))
    if result.dutbuild:
        print("  DUT build:", result.dutbuild)
    print("  Artifact location:", result.resultslocation)
    if result.arguments:
        print("Arguments:", result.arguments)
    if result.note:
        print("  NOTE:", result.note)
    for result in controllers.TestResultsController.subresults(result):
        _print_result_other(result, 0, False, True)
    print()


def _print_testcase_result(result, level, summarize, testcase_name=None):
    if result.result.is_passed():
        colorf = colors.green
    elif result.result.is_failed():
        colorf = colors.red
    else:
        colorf = colors.yellow
    name = result.testcase.name if (not testcase_name and result.testcase) else testcase_name
    if summarize:
        arguments = str(result.arguments) if result.arguments else "()"
        print(" " * level, "{}({}): {}".format(colors.green(name), arguments,
                                               colorf(str(result.result))))
        return
    print(" " * level, colors.green(name), "=>", colorf(str(result.result)))
    if result.testversion:
        print(" " * level, "  Version:", result.testversion)
    if result.arguments:
        print(" " * level, "Arguments:", result.arguments)
    print(" " * level, "    Start:", result.starttime)
    print(" " * level, "      End:", result.endtime)
    if result.endtime:
        print(" " * level, "  Elapsed:", result.endtime - result.starttime)
    if result.diagnostic:
        print(" " * level, colors.magenta("  Diagnostic:"))
        if "\n" in result.diagnostic:
            print(result.diagnostic)
        else:
            print(_medium_text_wrapper.fill(result.diagnostic))
    if result.note:
        print(" " * level, colors.white("  Note:"))
        print(_medium_text_wrapper.fill(result.note))
    if result.data is not None:
        print(" " * level, "  Has data.")
    print()


def _print_suite_result(result, level, failures, summarize):
    if result.result.is_passed():
        colorf = colors.green
    elif result.result.is_failed():
        colorf = colors.red
    else:
        colorf = colors.yellow
    if result.testsuite:
        print(" " * level, colors.yellow(result.testsuite.name), "=>", colorf(str(result.result)))
    else:
        print(" " * level, colors.yellow("bases.TestSuite"), "=>", colorf(str(result.result)))
    if not summarize:
        print(" " * level, "    Start:", result.starttime)
        print(" " * level, "      End:", result.endtime)
        if result.endtime:
            print(" " * level, "  Elapsed:", result.endtime - result.starttime)
        if result.note:
            print(" " * level, colors.white("  Note:"))
            print(_medium_text_wrapper.fill(result.note))
    print(" " * level + "  " + colors.underline("Tests:"))
    for result in controllers.TestResultsController.subresults(result, failures=failures):
        _print_result_other(result, level + 1, failures, summarize)
    print()


def _print_result_other(result, level, failures, summarize):
    if result.resulttype == controllers.TestResultsController.RESULT_TYPE_MAP["suite"]:
        _print_suite_result(result, level + 1, failures, summarize)
    elif result.resulttype == controllers.TestResultsController.RESULT_TYPE_MAP["test"]:
        _print_testcase_result(result, level + 1, summarize)


def show_testresult_logs(tr):
    rl = tr.resultslocation
    if rl and os.path.isdir(rl):
        print("Contents of:", rl)
        for de in os.scandir(rl):
            print(_format_directory_entry(de))
    else:
        print("Results location does not exist.")


def _format_directory_entry(de):
    st = de.stat()
    ts = time.strftime("%F %H:%M:%S", time.localtime(st.st_mtime))
    return "  0o{:03o} {:>10d} {} {}{}".format(st.st_mode & 0o777, st.st_size, ts, de.name,
                                               '/' if de.is_dir() else '')
