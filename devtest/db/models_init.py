# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Create and initialize the equipment models database.
"""

import sys

from . import models
from .util import create_db

database = models.database


def do_default_testbed(database):
    models.TestBed.create(name="default")
    database.commit()


# Some typical functions
def do_function(database):
    for name, desc in (
        ("DUT", "Device Under Test."),
        ("SUT", "Software Under Test."),
        ("router", "Provides IP routing service."),
        ("bridge", "Provides layer 2 bridging."),
        ("proxy", "A type of network protocol proxy."),
        ("browser", "Can render web content."),
        ("httpserver", "Serves web pages and content."),
        ("dnsserver", "Responds to DNS queries."),
        ("database", "A database server."),
        ("tftpserver", "Provides TFTP server"),
        ("nfsserver", "An NFS server."),
        ("ntpserver", "Provides network time sync service."),
    ):
        models.Function.create(name=name, description=desc)
    database.commit()

    for name, desc, impl in ():
        models.Function.create(name=name, description=desc, role_implementation=impl)
    database.commit()


def do_equipment_models(database):
    manufacturer = "Acme Inc."
    for name, attribs in ():
        models.EquipmentModel.create(name=name, manufacturer=manufacturer, attributes=attribs)
    database.commit()


def init_database(url):
    global database
    create_db(url)

    models.connect(url)
    database = models.database
    database.create_tables(
        [getattr(models, name) for name in models.TABLES + models._ASSOC_TABLES],  # noqa
        safe=False)
    try:
        do_default_testbed(database)
        do_function(database)
        do_equipment_models(database)
    finally:
        database.close()
        models.database = None


def _get_db_url():
    from devtest import config
    s = config.get_config()
    return s["database"]["url"]


def main(argv):
    url = argv[1] if len(argv) > 1 else _get_db_url()
    if url:
        init_database(url)


if __name__ == "__main__":
    main(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
