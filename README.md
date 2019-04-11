# General Purpose Device and System Test Framework

A generalized framework for testing systems of interconnected devices. It's
called *devtest*, short for device testing.

It provides a developer friendly API, reporting, and advanced debugging.

The framework models device types, equipment models, interfaces, connections,
and roles.  Group the device models into a Testbed objects for use by
generalized tests.  Test cases have easy access to this model to know about the
testbed and device attributes. Test cases may therefore be written more
abstractly and function properly in many testbed environments without change.

This is a multi-device, multi-interface, multi-role framework. It can manage
small scale testing of one device, up to large and complex test scenarios with
many heterogeneous devices and servers.


## Basic Installation

This is just a quick cheatsheet on getting setup so that it basically runs.
More documentation is coming.

### Dependencies

This framework requires Python 3.6 or greater.

The current default configuration expects a PostgreSQL database to be running
locally. It's also possible to configure a central, shared database server.
For this basic installation a local server can be used.

Other databases may be used in the future, once appropriate extensions are
written for the *peewee* ORM.

It is developed on and for Posix type systems, and tested on Linux and
MacOS/Darwin. It does not require a graphical environment, therefore runs just
fine on "headless" lab servers. Some test cases may have additional
dependencies, but the base framework has relatively few.

#### Linux

##### Debian or Ubuntu

You'll need the PostgreSQL server.

```console
$ sudo apt-get install postgresql
```

Configure it to listen on _localhost_ with _trust_ authorization.

###### libusb

You'll need the libusb dev package to compile the usb extension module.

```console
$ sudo apt-get install libusb-1.0-0-dev
```

#### OSX/MacOS

I use [homebrew](https://brew.sh/) to install dependencies. Please make sure
that is installed first.

After installing, make sure to install, as follows:

```console
$ brew install git
$ brew install libusb
$ brew install postgresql
$ brew services start postgresql
```

### Python

This framework needs Python 3.6 or later.  Use whatever host package manager you
use to install it.

#### Linux

On many Linux distros you can do this:

```console
$ sudo apt-get install python3.6-dev
```

#### MacOS

On MacOS with homebrew:

```console
$ brew install python      # default is latest Python 3 now (3.7), which is good.
```

That will get you everything you need to start.

### Python Packages

To make sure we use the Python version we want, we can set PYTHONBIN to point to
it.

```console
$ export PYTHONBIN=/usr/bin/python3.6  # or wherever your installation is.
```

That will probably be python3.7 on MacOS, as of this writing. That's fine.

Now install some necessary Python packages.

```console
# With brew on MacOS, everything is installed as regular user.
$ [[ $(uname) = Darwin ]] && SUDO="" || SUDO=sudo
$ $SUDO $PYTHONBIN -m pip install -U setuptools
$ $SUDO $PYTHONBIN -m pip install cython
$ $SUDO $PYTHONBIN -m pip install flake8
```

### Devtest

Here we'll clone from the source so you can stay up to date easily. Right
now, there is no installable package. You can run from the source tree, after
cloning it with git.

```console
# If you have access to private github repo:
$ git clone https://github.com/kdart/devtest.git
```

Now change into the new directory.

```console
$ cd devtest
```

Then verify we have the right Python, and set up *developer mode* for the framework source.

```console
$ make info
```

Verify that it will use the Python you want (3.6 or greater) If it looks good:

```console
$ make develop
```

Initialize the database.

```console
$ $PYTHONBIN -m devtest.db.models_init
```

This should create a PostgreSQL user named *devtest* and a database named
*devtest*. It will ask for your password, if you are on Linux, since it runs
*sudo* to do this.

Test that the installation and initialization worked. If it doesn't, check your
PostgreSQL installation and verify that it is listening on *localhost* and has
*trust* access in the _pghba.conf_ file.


```console
$ devtestadmin testbed list
default
```

If that works, it should be good to go. If not, well PostgreSQL can be difficult
to set up if you haven't done it before. Ask the author for help if you need to.

### Test Cases

Now you'll need a *testcases* package. The actual test cases are not included in
devtest. It expects to find a set of packages rooted at a *testcases* package
name. A basic template to get started can be installed from
[devtest-testcases](https://github.com/kdart/devtest-testcases).

Install it as follows.

```console
$ cd ~/src
$ git clone https://github.com/kdart/devtest-testcases
$ cd devtest-testcases
$ $PYTHONBIN setup.py develop --user
```

Now, try running a demo test case.

```console
$ devtester testcases.examples.demo.PassCheck
```

List available test cases with the `-l` option.

```console
$ devtester -l

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

#### Namespace Package

The *testcases* package is a namespace package. The *devtest-testcases* setup
can be used as a template for your own packages of test cases. It will also be
rooted in the *testcases* base package, but distributed separately. 


### Data Model

Eventually, you'll have to populate the database with your equipment model,
which includes testbeds, networks, interfaces, and connections.  Right now, the
*devtestadmin* tool is the only way to do that. Crude, but effective.

```console
$ devtestadmin
```

Will show the rather large usage. A better, possibly web based, UI is in the
dreaming stage.

#### Example session

```console
# Create an equipment model, which is a type of equipment.
devtestadmin eqmodel create "Pixel XL" Google

# Create a specific equipment instance.
devtestadmin eq create Google "Pixel XL" my_pixel2xl

# Oops, forgot the serial number. Update the equipment.
devtestadmin eq update Google my_pixel2xl  --serno=$ANDROID_SERIAL

# Create the DUT role
devtestadmin function create DUT

# Set it to be an Android implementation
devtestadmin function update DUT --implementation=devtest.devices.android.controller.AndroidController

# Add it to the default testbed as the DUT
devtestadmin testbed default add my_pixel2xl DUT
```

Now, in a test case implementation, you should be able to refer to it like this.

```python3

    def procedure(self):
        dut = self.testbed.DUT
        self.info(dut)
```

That is a "model object". It has information about the device, and you can add
more. To interact with it requires getting the *device* attribute.

```python3
    def procedure(self):
        dut = self.testbed.DUT
        self.info(dut)
        dev = dut.device
        self.info(dev.shell("ls /"))
        self.passed("Run ls command")
```

The Android device also has access to *adb*, *uiautomator*, the SL4A *api*, and
*snippets* by attribute accessors.

### Running Test Cases

Running test cases uses the *devtester* tool to inspect and run any test case.
You never write stand-alone scripts in this framework. They are proper Python
modules in a subpackage of *testcases* base package.

You can select a *Scenario* object that you define, or a single test cases. You
may also construct on the command-line a series of tests as an *ac hoc* test suite.

```console
$ devtester -h
```

Shows the help screen.

```
devtester [options] [-c <configfile>]
    [<globalconfig>...] [<testname> [<testconfig>]] ...

Select and run tests or test suites from the command line.

The globalconfig and testconfig arguments are in long option format
(e.g. --arg1=val1).

Options:

    -h  - This help.
    -l  - List available tests.
    -v  - Be more verbose, if possible.
    -c  - Additional YAML config file to merge into configuration.
    -C  - Show configuration, after overrides applied.
    -S  - Show information about selected test case (source) and exit.
    -L  - List available testbeds.
    -R  - List available reports that may be used to direct output to.
    -d  - Debug mode. Enter a debugger if a test has an error other
          than a failure condition.
    -D  - Debug framework mode. Enter a debugger on uncaught exception within runner.
    -E  - Show stderr during run. By default stderr is redirected to a file.
          Also enables logging to stderr.
    -K  - Keep any temporary files or directories that modules might create.
    -P  - Interactively pick a test to run.
    -T  - Interactively pick a testbed to run on.
    -r <x> - Repeat targeted test object this many times. Default 1.

Example:

  devtester -d --reportname=default --testbed=mytestbed --global1=globalarg testcases.mytest --mytestopt=arg
```

The *devtest-testcases* package contains a `_template.py` file to start from.
Copy that to another name, possibly in another subpackage, and edit it.

### Debugger

The framework allows choosing which debugger you want to use. It's configured
through the environment variable *PYTHON\_DEBUGGER*. It defaults to the built-in
*pdb* module. For a better debugging experience set it to "elicit.debugger".

```console
$ export PYTHON_DEBUGGER=elicit.debugger
```

Better put that in your *.bashrc* or *.zshrc* file.


## Continuing on...

That's the basics. There is much more to it than that. Feel free to contact the
author if you want to get started with it.

