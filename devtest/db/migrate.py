# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Support for database schema changes.

Example::

    from devtest.db.fields import *
    from devtest.db import migrate

    # create field objects as they appear in models.
    owners = ArrayField(null=True)

    db, migrator = migrate.get_migrator()

    with db.transaction():
        migrate.migrate(
                migrator.add_column("test_suites", "owners", owners),
                migrator.add_column("test_cases", "owners", owners),
                )
"""

from __future__ import generator_stop

from playhouse.migrate import PostgresqlMigrator, migrate  # noqa

from . import util


def connect(url=None, autocommit=False):
    if not url:
        from devtest import config
        cf = config.get_config()
        url = cf["database"]["url"]
    database = util.get_database(url, autocommit=autocommit)
    return database


def get_migrator(url=None):
    db = connect(url)
    migrator = PostgresqlMigrator(db)
    return db, migrator


if __name__ == "__main__":
    db, migrator = get_migrator()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
