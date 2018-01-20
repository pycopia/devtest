"""
Dynamic pages for the database app.
"""

# Flask requires this style of imports.

from devtest import logging

from flask import Flask


app = Flask(__name__)
app._logger = logging.Logger(app.logger_name)

# Needs to be last.
from . import views  # noqa
