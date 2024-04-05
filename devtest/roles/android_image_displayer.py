#!/usr/bin/env python3.6

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Controller role that displays images on an Android device screen.
"""

import os
import mimetypes

from devtest.devices.android import controller

from . import BaseRole


class ImageDisplayer(BaseRole):
    r"""Display images on a phone.

    Use the photos app to display a graphic that is pushed to the device acting
    as the display role.

    To use:

        Add a role such as "displayer":

            $ devtestadmin function create displayer \
                    --description="Display images on some kind of screen" \
                    --implementation=devtest.roles.android_image_displayer.ImageDisplayer
            $ devtestadmin testbed <testbed> add <mydisplayandroid> displayer
    """

    DESTINATION_DEFAULT = "/sdcard/Pictures"  # TODO(dart) query device
    BRIGHTNESS_DEFAULT = 64

    def initialize(self):
        self._controller = controller.AndroidController(self._equipment)
        self.destdir = self.config.get("destdir", ImageDisplayer.DESTINATION_DEFAULT)
        # turn off auto brightness and dim screen so target doesn't get washed
        # out.
        brightness = self.config.get("brightness", ImageDisplayer.BRIGHTNESS_DEFAULT)
        self._controller.settings.put("system", "screen_brightness_mode", False)
        self._controller.settings.put("system", "screen_brightness", brightness)

    def finalize(self):
        self._controller.buttons.home()

    def close(self):
        if self._controller is not None:
            self._controller.close()
            self._controller = None

    def prepare(self, filename, destdir=None):
        destdir = destdir or self.destdir
        filename = os.fspath(filename)
        filename = os.path.expandvars(os.path.expanduser(filename))
        mimetype, enc = mimetypes.guess_type(filename)
        remotepath = os.path.join(destdir, os.path.basename(filename))
        self._controller.adb.push([filename], destdir, sync=True)
        self._controller.buttons.power()
        return remotepath, mimetype

    def display(self, imagepath, destdir=None):
        remotepath, mimetype = self.prepare(imagepath, destdir)
        self._controller.buttons.back()  # undo previous display.
        self._controller.start_activity(action='android.intent.action.VIEW',
                                        data="file://" + remotepath,
                                        mimetype=mimetype)


if __name__ == "__main__":
    # Unit test case...
    import sys

    IMAGE = "~/tmp/english_business_card.png"
    SERNO = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ANDROID_SERIAL")

    class MockEquipment:

        def __init__(self, serno):
            self.serno = serno
            self._attribs = {
                "serno": serno,
                "role": "displayer",
            }

        def __getitem__(self, key):
            return self._attribs[key]

    displayer = ImageDisplayer(MockEquipment(SERNO))
    displayer.display(IMAGE)
    displayer.close()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
