#!/bin/bash

# Installer script that runs inside the docker build RUN entry.

set -e

PYTHONBIN=$(which python${PYVER})

mkdir -p /install
${PYTHONBIN} -m pip install --index-url ${PYPI_REPO} --trusted-host ${PYPI_HOST} --upgrade --ignore-installed -r /build/dev-requirements.txt
cd /build
tar xzf devtest-${VERSION}.tar.gz
cd devtest-${VERSION}
${PYTHONBIN} -m pip install --index-url ${PYPI_REPO} --trusted-host ${PYPI_HOST} --upgrade --ignore-installed --prefix=/install -r devtest.egg-info/requires.txt
${PYTHONBIN} setup.py install --single-version-externally-managed --root=/ --prefix=/install

# Install pre-built test cases package.
${PYTHONBIN} -m pip install --index-url ${PYPI_REPO} --trusted-host ${PYPI_HOST} --upgrade --prefix=/install devtest-testcases
