# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Run this package for a local web interface.
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
