"""
Where device controllers live.

Instantiated by the framework in devtest.db.testbeds, using
implementation configuration.
"""

from __future__ import generator_stop

import abc


class Controller(metaclass=abc.ABCMeta):
    def __init__(self, equipment):
        self._equipment = equipment


class Software(metaclass=abc.ABCMeta):
    def __init__(self, software):
        self._software = software
