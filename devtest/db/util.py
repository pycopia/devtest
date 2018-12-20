# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helpers for creating and maintaining the database.
"""

import os
import urllib.parse

from peewee import SqliteDatabase
from playhouse.postgres_ext import PostgresqlExtDatabase


# Map URL scheme names to database objects.
_DBSCHEMES = {
    'postgres': PostgresqlExtDatabase,
    'postgresql': PostgresqlExtDatabase,
    'sqlite': SqliteDatabase,
}


def create_db(url):
    url = urllib.parse.urlparse(url)
    scheme = url.scheme
    if scheme.startswith("postgres"):
        cmd = ('createuser --host {} --port {} '
               '--createdb --no-superuser --no-createrole {}'.format(
                   url.hostname, url.port or 5432, url.username))
        os.system(cmd)
        cmd = ('createdb --host {} --port {} --owner {} --encoding utf-8 {}'.format(
               url.hostname, url.port or 5432, url.username, url.path[1:]))
        os.system(cmd)
    elif scheme.startswith("sqlite"):
        import sqlite3
        db = sqlite3.connect(url.path)
        db.close()
    else:
        raise NotImplementedError("unhandled scheme: {}".format(scheme))


def drop_db(url):
    url = urllib.parse.urlparse(url)
    scheme = url.scheme
    if scheme.startswith("postgres"):
        cmd = ('dropdb --host {} --port {} -U {} {}'.format(
               url.hostname, url.port or 5432, url.username, url.path[1:]))
        os.system(cmd)
    elif scheme.startswith("sqlite"):
        os.unlink(url.path)
    else:
        raise NotImplementedError("unhandled scheme: {}".format(scheme))


def get_database(url, autocommit=False):
    """Connect to a backend database using the given URL."""
    url = urllib.parse.urlparse(url)
    dbclass = _DBSCHEMES.get(url.scheme)
    if dbclass is None:
        raise ValueError("Unsupported database scheme: {}".format(url.scheme))
    kwargs = {"autocommit": autocommit, "register_hstore": False}
    if url.scheme.startswith("postgres"):
        kwargs['database'] = url.path[1:]
        if url.username:
            kwargs['user'] = url.username
        if url.password:
            kwargs['password'] = url.password
        if url.hostname:
            kwargs['host'] = url.hostname
        kwargs['port'] = url.port or 5432
        kwargs['field_types'] = {'inet': 'inet',
                                 'cidr': 'cidr',
                                 'macaddr': 'macaddr'}
    else:
        kwargs['database'] = url.path
    return dbclass(**kwargs)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
