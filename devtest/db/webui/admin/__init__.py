"""
Basic DB admin webapp using generic Flask-Admin package.
"""

from devtest import logging

from flask import Flask
from flask_basicauth import BasicAuth


app = Flask(__name__)
app._logger = logging.Logger(app.logger_name)
app.secret_key = 'sKlSXXStEstbdlKD94$$kldspcwldkKDAld'

app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'devtest'
app.config['BASIC_AUTH_FORCE'] = True
app.config['SESSION_TYPE'] = 'filesystem'

# The Admin app doesn't need the basic_auth object externally, but a reference
# needs to be created to initialize the app with basic authentication.
basic_auth = BasicAuth(app)  # noqa
