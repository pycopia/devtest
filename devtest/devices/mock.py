"""
Mock device controller useful for testing and demo.
"""

from . import Controller


class MockController(Controller):

    def __init__(self, equipment):
        self._equipment = equipment
        self.name = "mock controller for {}".format(equipment.name)

    def __str__(self):
        return self.name

    def do_something(self):
        return "Did something on device."
