# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from glob import glob
import subprocess
from setuptools import setup, find_packages
from distutils.extension import Extension

from Cython.Distutils import build_ext

NAME = "devtest"
VERSION = "1.0"  # not used here.

SCRIPTS = glob("bin/*")
EXTENSIONS = [
    Extension('devtest.ringbuffer', ['src/ringbuffer.pyx'])
]

def get_pkgconfig_value(pkgname, option):
    cp = subprocess.run(['pkg-config', pkgname, option],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="ascii")
    return cp.stdout[2:].strip()  # chop flag prefixes


if sys.platform == "darwin":
    EXTENSIONS.append(Extension('devtest.timers', ['src/timers.pyx']))
elif sys.platform.startswith("linux"):
    EXTENSIONS.append(Extension('devtest.timers', ['src/timers.pyx'], libraries=["rt"]))
    EXTENSIONS.append(Extension('devtest.signals', ['src/signals.pyx'],
                                extra_compile_args=["-pthread"], libraries=["pthread"]))

# Build USB module if we can.
# need: "brew install libusb" on MacOS
# need libusb-1.0-dev package on Linux
LIBUSB_PKG = "libusb-1.0"

if subprocess.run(['pkg-config', LIBUSB_PKG, '--exists']).returncode == 0:
    includedir = get_pkgconfig_value(LIBUSB_PKG, '--cflags-only-I')
    libdir = get_pkgconfig_value(LIBUSB_PKG, '--libs-only-L')
    lib = get_pkgconfig_value(LIBUSB_PKG, '--libs-only-l')
    EXTENSIONS.append(Extension('devtest.usb',
                                ['src/libusb.pyx'],
                                library_dirs=([libdir] if libdir else None),
                                libraries=([lib] if lib else None),
                                include_dirs=([includedir] if includedir else None)))


setup(
    name=NAME,
    version=VERSION,
    packages=find_packages(exclude=("tests.*", "tests")),
    package_data={"devtest": ["*.yaml"]},
    scripts=SCRIPTS,
    test_suite="tests",
    tests_require=['pytest'],
    ext_modules=EXTENSIONS,
    cmdclass={"build_ext": build_ext},
    setup_requires=['setuptools_scm'],
    use_scm_version=True,

    license='Apache 2.0',
    description='General purpose device and system test framework.',
    long_description=open('README.md').read(),
    install_requires=[
        'blinker',
        'cryptography',
        'curio',
        'docopt',
        'docutils>=0.13',
        'peewee>=3.0',
        'portpicker',
        'psutil',
        'psycopg2',
        'pygments',
        'pyyaml',
        'numpy',
        'elicit>=1.7',
    ],
    author='Keith Dart',
    author_email='keith@dartworks.biz',
    url="https://github.com/kdart/devtest",
    classifiers=[
        "Programming Language :: Python",
        "License :: Apache 2.0",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Testing",
    ],
)
