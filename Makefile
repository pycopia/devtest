# Makefile simplifies some operations and supports common idioms.

# Set only major.minor version string, used elsewhere.
# Make sure your python3 is linked to the specific version you want.
PYTHONBIN ?= $(shell python3-config --prefix)/bin/python3

PYVER := $(shell $(PYTHONBIN) -c 'import sys;print("{}.{}".format(sys.version_info[0], sys.version_info[1]))')
ABIFLAGS := $(shell $(PYTHONBIN)-config --abiflags)
SUFFIX := $(shell $(PYTHONBIN)-config --extension-suffix)


OSNAME = $(shell uname)
# Assumes using python on darwin installed from homebrew
ifneq ($(OSNAME), Darwin)
	SUDO = sudo
else
	SUDO = 
endif

.PHONY: help info build install clean distclean develop test sdist \
	requirements publish extensions

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  info          Show info about the Python being used."
	@echo "  build         to just build the packages."
	@echo "  extensions    to build only extensions."
	@echo "  install       to install from this workspace."
	@echo "  develop       to set up for local development."
	@echo "  test          to run unit tests."
	@echo "  clean         to clean up build artifacts."
	@echo "  distclean     to make source tree pristine."
	@echo "  sdist         to build source distribution."

info:
	@echo Found Python version: $(PYVER)$(ABIFLAGS)
	@echo Specific Python used: $(PYTHONBIN)
	@echo Python extension suffix: $(SUFFIX)
	@echo sudo used: $(SUDO)

build:
	$(PYTHONBIN) setup.py build

extensions:
	$(PYTHONBIN) setup.py build_ext --inplace

install: build
	$(PYTHONBIN) setup.py install --skip-build --optimize

requirements:
	$(SUDO) $(PYTHONBIN) -m pip install -r dev-requirements.txt

develop: requirements
	$(PYTHONBIN) setup.py develop --user

test: extensions
	$(PYTHONBIN) setup.py test

clean:
	$(PYTHONBIN) setup.py clean
	find . -depth -type d -name __pycache__ -exec rm -rf {} \;

distclean: clean
	rm -rf .cache
	rm -rf devtest.egg-info
	rm -rf dist
	rm -rf build
	rm -f src/*.c
	find . -type f -name "*$(SUFFIX)" -delete

sdist: requirements
	$(PYTHONBIN) setup.py sdist

publish:
	$(PYTHONBIN) setup.py sdist upload
	$(PYTHONBIN) setup.py bdist_wheel upload
