"""Application controller mixins."""

from . import controller


class AppBase:
    """Base class for all applications."""

    def __init__(self, controller: controller.AndroidController):
        self._android = controller

    @property
    def android(self) -> controller.AndroidController:
        """The Android controller."""
        return self._android
