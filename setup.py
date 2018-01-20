
import sys
from glob import glob
from setuptools import setup, find_packages
from distutils.extension import Extension

from Cython.Distutils import build_ext

NAME = "devtest"
VERSION = "1.0"  # not used here.

SCRIPTS = glob("bin/*")
EXTENSIONS = [
    Extension('devtest.ringbuffer', ['src/ringbuffer.pyx'])
]

if sys.platform == "darwin":
    EXTENSIONS.append(Extension('devtest.timers', ['src/timers.pyx']))
elif sys.platform.startswith("linux"):
    EXTENSIONS.append(Extension('devtest.timers', ['src/timers.pyx'], libraries=["rt"]))

setup(
    name=NAME,
    version=VERSION,
    packages=find_packages(),
    package_data={"devtest": ["*.yaml"]},
    scripts=SCRIPTS,
    test_suite="tests",
    tests_require=['pytest'],
    ext_modules=EXTENSIONS,
    cmdclass={"build_ext": build_ext},
    # setup_requires=['setuptools_scm'],
    # use_scm_version=True,

    license='Apache 2.0',
    description='General purpose device and system test framework.',
    long_description=open('README.md').read(),
    install_requires=[
        'blinker',
        'cryptography',
        'curio',
        'docopt',
        'docutils>=0.13',
        'peewee>=2.8.2',
        'psutil',
        'psycopg2',
        'pygments',
        'pyyaml',
        'elicit>=1.2',
        # webui
        'flask',
        'Flask_BasicAuth',
        'flask_admin',
        'flask_cache',
        'wtf-peewee',
    ],
    author='Keith Dart',
    author_email='keith@dartworks.biz',
    url="https://github.com/kdart/devtest",
    classifiers=[
        "Programming Language :: Python",
        "License :: Apache 2.0",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Testing",
    ],
)
