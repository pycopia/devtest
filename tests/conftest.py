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
