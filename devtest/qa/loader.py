# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functions that find and load test modules.
"""

import os
import sys

import pkg_resources

from .. import importlib
from .. import logging


class Package:
    def __init__(self, name, version, location, filelist):
        self.name = name
        self.version = version
        self.location = location
        self.filelist = filelist

    def has_file(self, pathname):
        name = pathname[len(self.location) + 1:]
        return name in self.filelist


def find_packages(basename):
    for dist in pkg_resources.working_set:
        if dist.project_name.startswith(basename):
            if dist.has_metadata('RECORD'):
                lines = dist.get_metadata_lines('RECORD')
                file_list = [l.split(',')[0] for l in lines]
                yield Package(dist.project_name, dist.version, dist.location, file_list)

            elif dist.has_metadata('SOURCES.txt'):
                file_list = dist.get_metadata_lines('SOURCES.txt')
                yield Package(dist.project_name, dist.version, dist.location, file_list)


def get_package_version_from_module(mod):
    pathname = os.path.realpath(mod.__file__)
    for pkg in find_packages(mod.__name__.split(".")[0]):
        if pkg.has_file(pathname):
            return pkg.version


def load_selections(selections):
    """Take a list of OptionSet objects and return a list of runnable
    objects, with options attached.

    Returns a tuple of found objects and errored object selections.
    """
    selist = []
    errlist = []
    for selection in selections:
        try:
            obj = importlib.get_object(selection.argument)
        except (ImportError, AttributeError) as ierr:
            logging.warning("Could not find: {}: {}".format(
                            selection.argument, ierr))
            errlist.append(selection)
        else:
            obj.options = selection.options
            if type(obj) is type:
                obj.version = get_package_version_from_module(sys.modules[obj.__module__])
            else:
                obj.version = get_package_version_from_module(obj)
            selist.append(obj)
    return selist, errlist

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
