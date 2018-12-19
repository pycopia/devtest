# General Purpose Device and System Test Framework

A generalized framework for testing systems of interconnected devices.

Provides a developer friendly API, reporting, and advanced debugging.

The framework models device types, equipment models, interfaces, connections,
and roles.  Group the devices models into a Testbed objects for use by
generalized tests.  Test cases have easy access to this model to know about the
testbed and device attributes. Test cases may therefore be written more
abstractly and function properly in many testbed environments without change.

This is a multi-device, multi-interface, multi-role framework. It man manage
small scale testing, or large and complex test scenarios.


## Basic Installation

This is just a quick cheatsheet on getting setup so that it basically runs.
More documentation is coming.

### Dependencies

This framework requires Python 3.6 or greater.

The current default configuration expects a postgresql database to be running.
Other databases may be used in the future, once appropriate extensions are
written for the *peewee* ORM.

It is developed on and for Posix type systems, and tested on Linux and
MacOS/Darwin. It does not require a graphical environment, therefore runs just
fine on "headless" lab servers.

### OSX/MacOS

I use [homebrew](https://brew.sh/) to install dependencies. Please make sure
that is installed first.

After installing, make sure to install, as follows:

```shell
$ brew install git
$ brew install python      # default is latestPython 3 now, which is good.
$ brew install postgresql
$ brew services start postgresql
```

### Linux

#### Debian or Ubuntu

You'll need the postgres server.

```shell
$ sudo apt-get install postgresql
```

##### libusb

You'll need the libusb dev package to compile extension module.

```shell
$ sudo apt-get install libusb-1.0-0-dev
```

### Python Dependencies

Now install some necessary Python packages.

```shell
$ python3 -m pip install cython
$ python3 -m pip install flake8
```

### Devtest

Here we'll clone from the source so you can more easily stay up to date. Right
now, there is no installable package. You can run from the source tree, after
cloning it with git.

```shell
$ git clone https://github.com/kdart/devtest.git
$ cd devtest
```

To make sure we use the Python version we want, we can set PYTHONBIN to point to
it.

```shell
$ export PYTHONBIN=/usr/local/bin/python3.6  # or whereever your brew home is.
```

Then verify we have the right Python, and set up *developer mode* for the framework source.

```shell
$ make info
```

Verify that it will use the Python you want (3.6 or greater) If it looks good:

```shell
$ make develop
```

Initialize the database.

```shell
$ python3 -m devtest.db.models_init
```

This should create a postgres user *devtest* and a database named *devtest*.

Test that the installation and initialization worked. If it doesn't, check your
postgres installation and verify that it is listening on *localhost* and has
*trust* acess in the _pghba.conf_ file.


```shell
$ devtestadmin testbed list
default
```

If that works, it should be good to go.

Now you'll need a *testcases* package. The actual test cases are not included in
devtest. It expects to find a set of packages rooted at *testcases* package
name. A basic template to get started can be installed from
[devtest-testcases](https://github.com/kdart/devtest-testcases).


### Data Model

Eventually, you'll have to populate the database with your equipment model,
which includes testbeds, networks, interfaces, and connections.  Right now, the
*devtestadmin* tool is the only way to do that. Crude, but effective.

```shell
$ devtestadmin
```

Will show the usage. A better, possibly web based, UI is in the dreaming stages.

#### Example session

```console
# Create an equipment model, which is a type of equipment.
devtestadmin eqmodel create "Pixel 2" Google
devtestadmin eqmodel create "Pixel 2 XL" Google

# Create a specific equipment instance.
devtestadmin eq create Google "Pixel 2 XL" my_pixel2xl

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
more. To interact with it requires getting the device attribute.

```python3
    def procedure(self):
        dut = self.testbed.DUT
        self.info(dut)
        dev = dut.device
        self.info(dev.shell("ls /"))
        self.passed("Run ls command")
```

### Running Test Cases

Running test cases uses the *devtester* tool to inspect and run any test case.
You never write stand-alone scripts in this framework. They are proper Python
modules in a subpackage of *testcases* base package.

You can select a *Scenario* object that you define, or a single test cases. You
may also construct on the command-line a series of tests as an *ac hoc* test suite.

```shell
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


## Continuing on...

That's the basics. There is much more to it than that. Feel free to contact the
author if you want to get started with it.

