"""
Use Flask Admin to provide quick, generic interface to database.
"""

from __future__ import generator_stop

from . import app
from . import views


views.initialize_app(app)

print("http://localhost:5000/admin/")
print("admin : devtest")
app.run(debug=True, host="0.0.0.0", use_reloader=False)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
