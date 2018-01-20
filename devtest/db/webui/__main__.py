"""
Run this package for a local web interface.
"""

from __future__ import generator_stop


from .. import models
from . import app

models.connect()


@app.before_request
def _db_connect():
    models.database.connect()


@app.teardown_request
def _db_close(exc):
    if not models.database.is_closed():
        models.database.close()


app.run(debug=True, use_reloader=False)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
