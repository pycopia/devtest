# General Purpose Device and System Test Framework

A generalized framework for testing systems of interconnected devices.
It's called *devtest*, short for device testing. Note that it is NOT a unit test
framework for Python. The requirements for a device testing framework are quite
different from a unit test framework.

This is a multi-device, multi-interface, multi-role framework. It can manage
small scale testing of one device, up to large and complex test scenarios with
many heterogeneous devices and servers.

This package provides:

- A developer friendly API for writing test cases and scenarios.
- Supports large, complex device environments (testbeds).
- Supports manual tests that require human interaction.
    - You may mix manual and automated tests in a suite.
- Flexible result reporting
- Test case management and documentation generation.
    - Test case discovery
    - Automated test case documentation.
- Advanced debugging
- Many supporting modules for writing new device controllers.
    - USB interfaces
    - Serial interfaces
    - SSH client
    - Protocol modules
- Some built-in device controllers
    - Android
    - Linux hosts and servers

The framework models device types, equipment models, interfaces, connections, and roles in a
database.  Group the device models into Testbed objects for use by generalized tests.  Test cases
have easy access to this model to know about the testbed and device attributes, often using dynamic
properties. Test cases may therefore be written more abstractly and function properly in many
testbed environments without change.

## Basic Installation

This is just a quick cheatsheet on getting setup so that it basically runs.
More documentation is coming.

### Dependencies

This framework requires Python 3.10 or greater.

The current default configuration expects a PostgreSQL database to be running
locally. It's also possible to configure a central, shared database server.
For a basic installation a local server can be used.

It is developed on and for Posix type systems, and tested on Linux and
MacOS/Darwin. It does not require a graphical environment, therefore runs just
fine on "headless" lab servers. Some test cases may have additional
dependencies, but the base framework has relatively few.

## Development

Set up a development environment.

### Linux

#### Debian or Ubuntu

You'll need the PostgreSQL server.

```console
sudo apt-get install postgresql
```

Configure it to listen on _localhost_ with _trust_ authorization.

##### libusb

You'll need the libusb dev package to compile the usb extension module.

```console
sudo apt-get install libusb-1.0-0-dev
```

#### OSX/MacOS

I use [homebrew](https://brew.sh/) to install dependencies. Please make sure
that is installed first.

After installing, make sure to install, as follows:

```console
brew install git
brew install libusb
brew install postgresql
brew services start postgresql
```

### Python

This framework needs Python 3.10 or later.  Use whatever host package manager you
use to install it.

#### Linux Python

On many Linux distros you can do this:

```console
sudo apt-get install python3.10-dev
```

#### MacOS Python

On MacOS with homebrew install the latest Python 3, which should work here.

```console
brew install python
```

That will get you everything you need to start.

### Python Packages

To make sure we use the Python version we want, in case you have multiple versions installed, we can
set PYTHONBIN to point to it.

```console
export PYTHONBIN=/usr/bin/python3.10  # or wherever your installation is.
```

Now install some necessary Python packages, preferably in a Python virtual environment.

```console
# With brew on MacOS, everything is installed as regular user.
[[ $(uname) = Darwin ]] && SUDO="" || SUDO=sudo
$SUDO $PYTHONBIN -m pip install -U pip
$SUDO $PYTHONBIN -m pip install -U setuptools
$SUDO $PYTHONBIN -m pip install -U setuptools_scm
$SUDO $PYTHONBIN -m pip install keyring
$SUDO $PYTHONBIN -m pip install semver
$SUDO $PYTHONBIN -m pip install invoke
```

### Devtest

Here we'll clone from the source so you can stay up to date easily.
You can run from the source tree, after cloning it with git.

```console
git clone https://github.com/pycopia/devtest.git
```

You will need a configuration file. The basic configuration is in `~/.config/devtest/config.yaml`.
You will need at least enough configuration to "bootstrap" the database.

```console
$EDITOR ~/.config/devtest/config.yaml
```

Add this content to get started:

```yaml
database:
    select:
        "local"
    prod:
        url: "postgresql://devtest:devtest@postgserver/devtest"
    local:
        url: "postgresql://localhost/devtest"
```

You can always alter or move the server location later.

Now change into the new directory.

```console
cd devtest
```

Then verify we have the right Python, and set up *developer mode* for the framework source.

```console
invoke info
```

Verify that it will use the Python you want (3.6 or greater) If it looks good:

```console
invoke develop
```

Initialize the database.

```console
$PYTHONBIN -m devtest.db.models_init
```

This should create a PostgreSQL user named *devtest* and a database named
*devtest*. It will ask for your password, if you are on Linux, since it runs
*sudo* to do this.

Test that the installation and initialization worked. If it doesn't, check your
PostgreSQL installation and verify that it is listening on *localhost* and has
*trust* access in the _pg_hba.conf_ file.

```console
devtestadmin testbed list
```

Should show `default`.

If that works, it should be good to go. If not, well PostgreSQL can be difficult
to set up if you haven't done it before. Ask the author for help if you need to.

### Test Cases

Now you'll need a *testcases* package. The actual test cases are not included in
devtest. It expects to find one or more namespace packages starting with the *testcases* name.
A basic template to get started can be installed from
[devtest-testcases](https://github.com/pycopia/devtest-testcases).

Install it as follows, preferably in your virtual environment.

```console
cd ~/src
git clone https://github.com/pycopia/devtest-testcases
cd devtest-testcases
invoke develop
```

List available test cases with the `-l` option.

```console
devtester -l

Runnable objects:
      test testcases.examples.demo.BasicReadinessCheck
  scenario testcases.examples.demo.DemoScenario
      test testcases.examples.demo.ErrorCheck
      test testcases.examples.demo.FailCheck
      test testcases.examples.demo.PassCheck
      test testcases.examples.eat.EatTheApple
  scenario testcases.examples.eat.EatingScenario
      test testcases.examples.interactive.InteractiveTest
```

Now, try running a demo test case.

```console
devtester testcases.examples.demo.PassCheck
```

#### Namespace Package

The *testcases* package is a namespace package. The *devtest-testcases* setup
can be used as a template for your own packages of test cases. It will also be
rooted in the *testcases* base package, but distributed separately.

### Data Model

Eventually, you'll have to populate the database with your equipment model, which includes testbeds,
networks, interfaces, and connections.  Right now, the *devtestadmin* tool is the only way to do
that. It's also possible to write database "importers" to populate it from existing equipment.

```console
devtestadmin
```

Will show the rather large usage.

#### Example session

Create an equipment model, which is a type of equipment.

Here we will set up a locally attached Android device.

```console
devtestadmin eqmodel create "Pixel XL" Google
```

##### Create a specific equipment instance

```console
devtestadmin eq create Google "Pixel XL" my_pixel2xl
```

Oops, forgot the serial number. Update the equipment.

```console
devtestadmin eq update Google my_pixel2xl  --serno=$ANDROID_SERIAL
```

##### Create the DUT role

```console
devtestadmin function create DUT
```

Set it to be an Android implementation:

```console
devtestadmin function update DUT --implementation=devtest.devices.android.controller.AndroidController
```

Add it to the default testbed as the DUT:

```console
devtestadmin testbed default add my_pixel2xl DUT
```

Now, in a test case implementation, you should be able to refer to it like this.

```python3

    def procedure(self):
        dut = self.testbed.DUT
        self.info(dut)
```

The `dut` is a "model object". It has information about the device, and you can add
more attributes. To interact with it requires getting the *device* attribute.

```python3
    def procedure(self):
        dut = self.testbed.DUT
        self.info(dut)
        self.info(dut.device.shell("whoami"))
        self.info(dut.device.listdir("/"))
        self.passed("Run commands and and listed directory.")
```

The Android device also has access to *adb*, *uiautomator*, the SL4A *api*, and
*snippets* by those attribute names.

### Running Test Cases

Running test cases uses the *devtester* tool to inspect and run any test case.
You never write stand-alone scripts in this framework. They are proper Python
modules in a subpackage of *testcases* base package.

You can select a *Scenario* object that you define, or a single test cases. You
may also construct on the command-line a series of tests as an *ac hoc* test suite.

```console
devtester -h
```

Shows the help screen.

```console
devtester [options] [-c <configfile>]
    [<globalconfig>...] [<testname> [<testconfig>]] ...

Select and run tests or test scenarios from the command line.

The globalconfig and testconfig arguments are in long option format
(e.g. --arg1=val1). The test runner options are all in the short, `-X`, form.

Options:

    -h  - This help.
    -l  - List available tests.
    -v  - Be more verbose, if possible. Increase verbosity for each occurence.
    -r <x> - Repeat targeted test object this many times. Default 1.
    -c  - Additional YAML config file to merge into configuration.
    -d  - Debug mode. Enter a debugger if a test has an error other
          than a failure condition.
    -D  - Debug framework mode. Enter a debugger on uncaught exception within runner.
    -E  - Show stderr during run. By default stderr is redirected to a file.
          Also enables logging to stderr.
    -I  - Do NOT run any tests marked INTERACTIVE. Default is to run them.
    -K  - Keep any temporary files or directories that modules might create.
    -P  - Interactively pick a test to run.
    -T  - Interactively pick a testbed to run on.
    -C  - Show configuration, after overrides applied.
    -S  - Show information about selected test case (source) and exit.
    -L  - List available testbeds.
    -R  - List available reports that may be used to direct output to.
    -s  - Enter a REPL (shell) in the context of a test case procedure. Specified tests are ignored.

Example:

    devtester -d --reportname=default --testbed=mytestbed --global1=globalarg \
        testcases.system.MyTest --mytestoption=arg

    That will run a test in debug mode (-d), select the report named "default", select the
    (pre-defined) test bed named "mytestbed", set global option "global1" to "globalarg, and select
    the testcase "testcases.system.MyTest. That test will get its own option in the `options`
    attribute with key "mytestoption", and argument "arg".

    If a test case procedure takes arguments, you can specify them with the `--args` option.

    devtester --testbed=mytestbed testcases.dev.CheckMyDevFlubber --args=procedurearg1,procedurearg2

Use the `-l` option to print a list of runnable objects there are found when scanned.
```

The *devtest-testcases* package contains a `_template.py` file to start from.
Copy that to another name, possibly in another subpackage, and edit it.

### Debugger

The framework has a built-in debugger, provided by the [elicit](https://pypi.org/project/elicit/)
package. When *devtester* is run with the `-d` flag the debugger is automatically invoked for any
uncaught exception.

## Continuing on

That's the basics. There is much more to it than that. Feel free to contact the
author if you want to get started with it.
