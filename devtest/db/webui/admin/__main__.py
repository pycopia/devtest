# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Use Flask Admin to provide quick, generic interface to database.
"""

from __future__ import generator_stop

from . import app
from . import views


views.initialize_app(app)

print("http://localhost:5000/admin/")
print("admin : devtest")
app.run(debug=True, host="0.0.0.0", use_reloader=False)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
