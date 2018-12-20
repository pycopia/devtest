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
pytest configuration and common code lives here.
"""

import os
import time
import shutil
import subprocess
from urllib import parse

import pytest


class DB:
    """Fixture that manages a local, temporary postgres server for unit testing."""
    DB_URL = "postgresql://devtest@localhost:5555/devtest_test"
    DB_DIR = "/var/tmp/devtest"
    pg_proc = None

    def __init__(self):
        os.makedirs(DB.DB_DIR, exist_ok=True)
        subprocess.run(['initdb', '-D', DB.DB_DIR, '-E', 'UTF-8'],
                       stdout=subprocess.DEVNULL, shell=False)
        url = parse.urlparse(DB.DB_URL)
        proc = subprocess.Popen(
            ['postgres', '-D', DB.DB_DIR, '-h', url.hostname, '-p', str(url.port), '-i'],
            shell=False, stdout=subprocess.DEVNULL)
        self.pg_proc = proc
        # need some time to bring up new db
        time.sleep(1)

    def __del__(self):
        self.close()

    def close(self):
        if self.pg_proc is not None:
            proc = self.pg_proc
            self.pg_proc = None
            proc.terminate()
            time.sleep(1)
            shutil.rmtree(DB.DB_DIR)


@pytest.fixture(scope="session")
def db(request):
    db = DB()
    request.addfinalizer(db.close)
    return db

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
