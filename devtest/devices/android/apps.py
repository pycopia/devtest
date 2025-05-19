"""Application controller mixins."""


class AppBase:
    """Base class for all applications."""

    def __init__(self, controller):
        self._android = controller

    @property
    def android(self):
        """The Android controller."""
        return self._android
