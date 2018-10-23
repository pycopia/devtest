# General Purpose Device and System Test Framework

A generalized framework for testing systems of interconnected devices.

Provides a developer friendly API, reporting, and advanced debugging.

The framework models device types, models, interfaces, connections, and roles.
Group the devices models into a Testbed objects for use by generalized tests.
Test cases have easy access to this model to know about the testbed and device
attributes. Test cases may therefore be written more abstractly and function
properly in many testbed environments without change.


## Basic Installation

This is just a quick cheatsheet on getting setup so that it basically runs.
More documentation is coming.

### Dependencies

This framework requires Python 3.6 or greater. 

The current default configuration expects a postgresql database to be running.
Other databases may be used in the future, once appropriate extensions are
written for the *peewee* ORM.

### OSX/MacOS

I use [homebrew](https://brew.sh/) to install dependencies. Please make sure that is installed first.

After installing, make sure to install, as follows:

```shell
$ brew install git
$ brew install python3
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

Here we'll clone from the source so you can more easily stay up to date.

```shell
$ git clone https://github.com/kdart/devtest.git
$ cd devtest
```

To make sure we use the Python version we want, we can set PYTHONBIN to point to it.

```shell
$ export PYTHONBIN=/usr/local/bin/python3.6  # or whereever your brew home is.
```

Then verify we have the right Python, and set up *developer mode* for the framework source.

```shell
$ make info
$ make develop
```

Initialize the database.

```shell
$ python3 -m devtest.db.models_init
```

Test that the installation and initialization worked.

```shell
$ devtestadmin testbed list
default
```

If that works, it should be good to go. Now you'll need a *testcases* package.

Eventually, you'll have to populate the database with your equipment model,
which includes testbeds, networks, interfaces, and connections.  Right now, the
*devtestadmin* tool is the only way to do that. Crude, but effective.

When you do, use the *devtester* tool to start any test case.

