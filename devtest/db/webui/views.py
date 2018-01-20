"""
Local test framework web views.
"""

from __future__ import generator_stop


from flask import (url_for, make_response, abort, redirect, request, session, g) # noqa

from . import app  # noqa


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
