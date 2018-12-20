# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Option parser that does not require pre-determined options. Collects short
options for global options, and collects long options as configuration
overrides.
"""

from ast import literal_eval


class OptionSet:
    """Used to hold command argument name and its options, as provided by a
    user interface.

    Attributes:
        argument (str): the argument name.
        options (dict): The key-value pairs of the long options associated with
                        the argument.
    """

    def __init__(self, argument=None, options=None):
        self.argument = argument
        self.options = options or {}

    def set_option(self, name, value):
        self.options[name] = value

    def __repr__(self):
        return "{}({!r}, {!r})".format(self.__class__.__name__,
                                       self.argument, self.options)


class ArgumentList(list):
    """Ordered container of OptionSet objects.
    """

    @property
    def arguments(self):
        """A list of only the non-option arguments, not including the first
        argument (the program name, usually).
        """
        return [a.argument for a in self[1:]]

    @property
    def program(self):
        return self[0].argument


class GetoptError(Exception):
    pass


def getopt(argv, shortopts):
    """Parse argv for short options and argument sets.

    Returns a list of tuples of the short options and their arguments, and a
    ArgumentList containing a sequence of OptionSet objects for each non-option
    argument and associated config options. Config options are expressed in
    long-option format.

    The first OptionSet is the command name itself and global config
    options.

    May raise our GetoptError if a problem with the short options is found.
    """
    argumentlist = ArgumentList()
    opts = []
    argit = iter(argv[:])
    currentset = None
    for arg in argit:
        if not arg:
            continue
        if arg.startswith("-"):
            if len(arg) == 1:
                raise GetoptError("Missing option character")
            if arg[1] == "-":
                name, val = _do_long(arg)
                currentset.set_option(name, val)
            else:  # short options
                for oc in arg[1:]:
                    for ci, c in enumerate(shortopts):
                        if c == oc:
                            try:
                                if shortopts[ci + 1] == ":":
                                    optarg = _eval(next(argit))
                                else:
                                    optarg = None
                            except IndexError:
                                optarg = None
                            opts.append((c, optarg))
                            break
                    else:
                        raise GetoptError(
                            "Got unexpected short argument: {}".format(oc))
        else:
            currentset = OptionSet(arg)
            argumentlist.append(currentset)

    return opts, argumentlist


def _do_long(opt):
    try:
        i = opt.index('=')
    except ValueError:
        return opt[2:], True
    return opt[2:i], _eval(opt[i + 1:])


def _eval(val):
    try:
        return literal_eval(val)
    except (ValueError, SyntaxError):
        return val


# Run as top-level script to unit test.
if __name__ == "__main__":
    argv = ["/usr/bin/prog", "-dv", "-v", "-s", "string", "name1",
            "--arg11=val11", "--arg12=val12", "name2", "name3", "--arg31",
            "--arg32=val32"]

    d = False
    v = 0
    s = None
    opts, arguments = getopt(argv, "dvs:")
    name = arguments[0].argument
    print("name:", name)
    print("options:", opts)
    print("arguments:", arguments)
    assert name == argv[0]
    for opt, optarg in opts:
        if opt == "d":
            d = True
        elif opt == "v":
            v += 1
        elif opt == "s":
            s = optarg
    assert d is True
    assert v == 2
    assert s == "string"
    assert len(arguments) == 4
    assert len(arguments[0].options) == 0
    assert len(arguments[1].options) == 2
    assert len(arguments[2].options) == 0
    assert len(arguments[3].options) == 2
    assert arguments[1].argument == "name1"
    assert arguments[2].argument == "name2"
    assert arguments[3].argument == "name3"

    try:
        opts, arguments = getopt(["prog", "-x"], "dvs:")
    except GetoptError as goe:
        assert goe.args[0].startswith("Got unexpected")
    else:
        raise AssertionError("didn't get expected error")

    argv = ["prog", "-dv", "argument"]
    opts, args = getopt(argv, "h?dv")
    print(opts, args)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
