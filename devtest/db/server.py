# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Start and manage a local postgresql server.

Used when a system-wide server is not available or desirable.
"""

import os
import time
import threading
import signal
import subprocess
from urllib import parse as url_parse

from devtest.os import procutils
from devtest.core import exceptions


class DatabaseServer(threading.Thread):
    """Manage a postgres server process.

    Supply the global configuration. The 'database.url' entry will be updated to
    reflect what should be used to reach it.
    """

    def __init__(self, config):
        super().__init__()
        self._dbdir = config.database.postgres.dbdir
        self.pg_proc = None
        config.database.url = create_database(self._dbdir)

    def run(self):
        # "unix_socket_directories=/tmp,{sockdir}".format(sockdir=sockdir)
        proc = subprocess.Popen(['postgres', '-D', self._dbdir], shell=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self.pg_proc = proc
        proc.wait()

    def close(self):
        if self.pg_proc is not None:
            proc = self.pg_proc
            self.pg_proc = None
            proc.send_signal(signal.SIGINT)

    def join(self, timeout=None):
        self.close()
        super().join(timeout=timeout)


def create_database(dbdir):
    username = "devtest"
    database = "devtest"
    url = "postgresql:///tmp/{database}?user={user}".format(database=database, user=username)
    if os.path.isdir(os.path.join(dbdir, "base")):
        return url
    os.makedirs(dbdir, exist_ok=True)
    subprocess.check_call(['initdb', '-D', dbdir, '-E', 'UTF-8'],
                          stdout=subprocess.DEVNULL, shell=False)

    proc = subprocess.Popen(['postgres', '-D', dbdir], shell=False, stdout=subprocess.DEVNULL)
    time.sleep(5)
    subprocess.check_call(['createuser', '--createdb', '--no-superuser', '--no-createrole', username],
                          stdout=subprocess.DEVNULL, shell=False)
    subprocess.check_call(['createdb', '--owner', username, '--encoding', 'utf-8', database],
                          stdout=subprocess.DEVNULL, shell=False)
    time.sleep(5)
    proc.terminate()
    proc.wait()
    return url


def installation_check():
    if procutils.which("postgres") and procutils.which("initdb"):
        return True
    return False


def start_server(config):
    if not installation_check():
        raise exceptions.MissingDependencyError("Can't find postgres program.")
    srv = DatabaseServer(config)
    srv.start()
    return srv


if __name__ == "__main__":
    from devtest import config
    from devtest.db import controllers

    cf = config.get_config()
    srv = start_server(cf)
    print("URL:", cf.database.url)
    time.sleep(3)
    controllers.connect()
    #for tb in controllers.TestBedController.all():
    #    print(tb)
    print("Waiting...")
    time.sleep(30)
    print("shutdown...")
    srv.join()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
