# Makefile simplifies some operations and supports common idioms.

# Set only major.minor version string, used elsewhere.
# Make sure your python3 is linked to the specific version you want.
PYVER := $(shell python3 -c 'import sys;print("{}.{}".format(*sys.version_info))')

PYTHON := $(shell python3-config --prefix)/bin/python$(PYVER)
SUFFIX := $(shell python3-config --extension-suffix)


.PHONY: help info build install clean distclean develop test sdist \
	requirements publish extensions

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  build         to just build the packages."
	@echo "  info          Show info about the Python used."
	@echo "  extensions    to build only extensions."
	@echo "  install       to install from this workspace."
	@echo "  develop       to set up for local development."
	@echo "  test          to run unit tests."
	@echo "  clean         to clean up build artifacts."
	@echo "  distclean     to make source tree pristine."
	@echo "  sdist         to build source distribution."

info:
	@echo Specific Python: $(PYTHON)
	@echo Python suffix: $(SUFFIX)

build:
	$(PYTHON) setup.py build

extensions:
	$(PYTHON) setup.py build_ext --inplace

install: build
	$(PYTHON) setup.py install --skip-build --optimize

requirements:
	sudo pip$(PYVER) install -r dev-requirements.txt

develop: requirements
	$(PYTHON) setup.py develop --user

test: extensions
	$(PYTHON) setup.py test

clean:
	$(PYTHON) setup.py clean
	find . -depth -type d -name __pycache__ -exec rm -rf {} \;

distclean: clean
	rm -rf .cache
	rm -rf devtest.egg-info
	rm -rf dist
	rm -rf build
	rm -f src/*.c
	find . -type f -name "*$(SUFFIX)" -delete

sdist: requirements
	$(PYTHON) setup.py sdist

publish:
	$(PYTHON) setup.py sdist upload
	$(PYTHON) setup.py bdist_wheel upload
