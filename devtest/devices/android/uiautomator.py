"""Python wrapper for Android uiautomator tool."""

# The MIT License (MIT)
# Copyright (c) 2013 Xiaocong He
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

import collections
from http.client import HTTPException, RemoteDisconnected
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.dom.minidom

import portpicker
from devtest import config
from devtest import json
from devtest import logging
from devtest.devices.android import adb

DEVICE_PORT = int(os.environ.get("UIAUTOMATOR_DEVICE_PORT", "9008"))
LOCAL_PORT = int(os.environ.get("UIAUTOMATOR_LOCAL_PORT", "9008"))

if "localhost" not in os.environ.get("no_proxy", ""):
    os.environ["no_proxy"] = f"localhost,{os.environ.get('no_proxy', '')}"

__authors__ = ["Xiaocong He", "Keith Dart"]
__all__ = [
    "AutomatorDevice",
    "rect",
    "point",
    "Selector",
    "JsonRPCError",
]


class Error(Exception):
    """Base error for UIAutomator."""


class UIAutomatorError(Error):
    """General error in UIAutomator interface."""


class JsonRPCError(Exception):
    """When the JSON-RPC protocol reports an error."""

    def __init__(self, code, message):
        self.code = int(code)
        self.message = message

    def __str__(self):
        return f"JsonRPC Error code: {self.code}, Message: {self.message}"


def param_to_property(*props, **kwprops):
    if props and kwprops:
        raise ValueError("Can not set both props and kwprops at the same time.")

    class Wrapper(object):

        def __init__(self, func):
            self.func = func
            self.kwargs, self.args = {}, []

        def __getattr__(self, attr):
            if kwprops:
                for prop_name, prop_values in kwprops.items():
                    if attr in prop_values and prop_name not in self.kwargs:
                        self.kwargs[prop_name] = attr
                        return self
            elif attr in props:
                self.args.append(attr)
                return self
            raise AttributeError(f"{attr} parameter is duplicated or not allowed!")

        def __call__(self, *args, **kwargs):
            if kwprops:
                kwargs.update(self.kwargs)
                self.kwargs = {}
                return self.func(*args, **kwargs)
            new_args, self.args = self.args + list(args), []
            return self.func(*new_args, **kwargs)

    return Wrapper


class JsonRPCMethod:

    def __init__(self, url, method, timeout=30):
        self.url, self.method, self.timeout = url, method, timeout

    def __call__(self, *args, **kwargs):
        if args and kwargs:
            raise ValueError("Could not accept both *args and **kwargs as JSONRPC parameters.")
        data = {"jsonrpc": "2.0", "method": self.method, "id": next(_counter)}
        if args:
            data["params"] = args
        elif kwargs:
            data["params"] = kwargs
        jsonresult = {"result": ""}
        result = None
        try:
            req = urllib.request.Request(
                self.url,
                json.encode_bytes(data),
                {"Content-type": "application/json"},
            )
            result = urllib.request.urlopen(req, timeout=self.timeout)
            jsonresult = json.decode_bytes(result.read())
        finally:
            if result is not None:
                result.close()

        if "error" in jsonresult and jsonresult["error"]:
            raise JsonRPCError(
                jsonresult["error"]["code"],
                "%s: %s" % (
                    jsonresult["error"]["data"]["exceptionTypeName"],
                    jsonresult["error"]["message"],
                ),
            )
        return jsonresult["result"]


def id_counter():
    i = 1
    while 1:
        yield i
        i += 1


_counter = id_counter()


class JsonRPCClient:

    def __init__(self, url, timeout=30, method_class=JsonRPCMethod):
        self.url = url
        self.timeout = timeout
        self.method_class = method_class

    def __getattr__(self, method):
        return self.method_class(self.url, method, timeout=self.timeout)


class Selector(dict):
    """The class is to build parameters for UiSelector passed to Android device."""

    __fields = {
        "text": (0x01, None),  # MASK_TEXT,
        "textContains": (0x02, None),  # MASK_TEXTCONTAINS,
        "textMatches": (0x04, None),  # MASK_TEXTMATCHES,
        "textStartsWith": (0x08, None),  # MASK_TEXTSTARTSWITH,
        "className": (0x10, None),  # MASK_CLASSNAME
        "classNameMatches": (0x20, None),  # MASK_CLASSNAMEMATCHES
        "description": (0x40, None),  # MASK_DESCRIPTION
        "descriptionContains": (0x80, None),  # MASK_DESCRIPTIONCONTAINS
        "descriptionMatches": (0x0100, None),  # MASK_DESCRIPTIONMATCHES
        "descriptionStartsWith": (0x0200, None),  # MASK_DESCRIPTIONSTARTSWITH
        "checkable": (0x0400, False),  # MASK_CHECKABLE
        "checked": (0x0800, False),  # MASK_CHECKED
        "clickable": (0x1000, False),  # MASK_CLICKABLE
        "longClickable": (0x2000, False),  # MASK_LONGCLICKABLE,
        "scrollable": (0x4000, False),  # MASK_SCROLLABLE,
        "enabled": (0x8000, False),  # MASK_ENABLED,
        "focusable": (0x010000, False),  # MASK_FOCUSABLE,
        "focused": (0x020000, False),  # MASK_FOCUSED,
        "selected": (0x040000, False),  # MASK_SELECTED,
        "packageName": (0x080000, None),  # MASK_PACKAGENAME,
        "packageNameMatches": (0x100000, None),  # MASK_PACKAGENAMEMATCHES,
        "resourceId": (0x200000, None),  # MASK_RESOURCEID,
        "resourceIdMatches": (0x400000, None),  # MASK_RESOURCEIDMATCHES,
        "index": (0x800000, 0),  # MASK_INDEX,
        "instance": (0x01000000, 0),  # MASK_INSTANCE,
    }
    __mask = "mask"
    __childOrSibling = "childOrSibling"
    __childOrSiblingSelector = "childOrSiblingSelector"

    def __init__(self, **kwargs):
        super(Selector, self).__setitem__(self.__mask, 0)
        super(Selector, self).__setitem__(self.__childOrSibling, [])
        super(Selector, self).__setitem__(self.__childOrSiblingSelector, [])
        for k in kwargs:
            self[k] = kwargs[k]

    def __setitem__(self, k, v):
        if k in self.__fields:
            super(Selector, self).__setitem__(k, v)
            super(Selector, self).__setitem__(self.__mask, self[self.__mask] | self.__fields[k][0])
        else:
            raise ReferenceError("%s is not allowed." % k)

    def __delitem__(self, k):
        if k in self.__fields:
            super(Selector, self).__delitem__(k)
            super(Selector, self).__setitem__(self.__mask, self[self.__mask] & ~self.__fields[k][0])

    def clone(self):
        kwargs = dict((k, self[k]) for k in self if k not in [
            self.__mask,
            self.__childOrSibling,
            self.__childOrSiblingSelector,
        ])
        selector = Selector(**kwargs)
        for v in self[self.__childOrSibling]:
            selector[self.__childOrSibling].append(v)
        for s in self[self.__childOrSiblingSelector]:
            selector[self.__childOrSiblingSelector].append(s.clone())
        return selector

    def child(self, **kwargs):
        self[self.__childOrSibling].append("child")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    def sibling(self, **kwargs):
        self[self.__childOrSibling].append("sibling")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    child_selector, from_parent = child, sibling


def rect(top=0, left=0, bottom=100, right=100):
    return {"top": top, "left": left, "bottom": bottom, "right": right}


def intersect(rect1, rect2):
    top = rect1["top"] if rect1["top"] > rect2["top"] else rect2["top"]
    bottom = (rect1["bottom"] if rect1["bottom"] < rect2["bottom"] else rect2["bottom"])
    left = rect1["left"] if rect1["left"] > rect2["left"] else rect2["left"]
    right = rect1["right"] if rect1["right"] < rect2["right"] else rect2["right"]
    return left, top, right, bottom


def point(x=0, y=0):
    return {"x": x, "y": y}


class NotFoundHandler:
    """Handler for UI Object Not Found exception.

  It's a replacement of UiAutomator watcher on device side.
  """

    def __init__(self):
        self.__handlers = collections.defaultdict(lambda: {"on": True, "handlers": []})

    def __get__(self, instance, type):
        return self.__handlers[instance._adb.serial]


class AutomatorServer:
    """start and quit RPC server on device."""

    handlers = NotFoundHandler()  # handler UI Not Found exception

    def __init__(
        self,
        serial,
        local_port=None,
        device_port=None,
        adb_server_host="localhost",
        adb_server_port=adb.ADB_PORT,
        serversource="google",
    ):
        self._sdk = 0
        self._uia_device_process = None
        self._adb = adb.AndroidDeviceClient(serial, host=adb_server_host, port=adb_server_port)
        self.device_port = int(device_port) if device_port else DEVICE_PORT
        self._local_port = int(local_port) if local_port else None
        self.host = adb_server_host
        self.serial = serial
        self.source = serversource

    def __del__(self):
        self.close()

    def get_forwarded_port(self):
        """Returns local port which is already forwarded for `self.device_port`."""
        for lp, rp in self._adb.list_forward():
            if rp == self.device_port:
                return lp
        return None

    @property
    def local_port(self):
        """Selects a local port.

    Returns:
      int, local port ready for use.
    """
        if not self._local_port:
            forwarded_port = self.get_forwarded_port()
            if forwarded_port:
                self._local_port = forwarded_port
            else:
                self._local_port = portpicker.pick_unused_port()
        return self._local_port

    def forward_port(self):
        self._adb.forward(self.local_port, self.device_port)

    def forward_remove(self):
        self._adb.kill_forward(self.local_port)

    def install(self):
        cf = config.get_config()
        base_dir = os.path.dirname(__file__)
        for apk in cf.uiautomator[self.source].apks:
            print(apk)  # XXX use resource api
            # self._adb.install(os.path.join(base_dir, "lib", apk))

    @property
    def jsonrpc(self):
        return self.jsonrpc_wrap(timeout=90)

    def jsonrpc_wrap(self, timeout):
        server = self
        ERROR_CODE_BASE = -32000

        def _JsonRPCMethod(url, method, timeout, restart=True):
            _method_obj = JsonRPCMethod(url, method, timeout)

            def wrapper(*args, **kwargs):
                URLError = urllib.error.URLError
                try:
                    return _method_obj(*args, **kwargs)
                except (URLError, HTTPException, IOError):
                    if restart:
                        server.stop()
                        server.start(timeout=30)
                        return _JsonRPCMethod(url, method, timeout, False)(*args, **kwargs)
                    raise
                except JsonRPCError as e:
                    if e.code >= ERROR_CODE_BASE - 1:
                        server.stop()
                        server.start()
                        return _method_obj(*args, **kwargs)
                    if e.code == ERROR_CODE_BASE - 2 and self.handlers["on"]:  # Not Found
                        try:
                            self.handlers["on"] = False
                            # any handler returns True will break the left handlers
                            any(
                                handler(self.handlers.get("device", None))
                                for handler in self.handlers["handlers"])
                        finally:
                            self.handlers["on"] = True
                        return _method_obj(*args, **kwargs)
                    raise

            return wrapper

        return JsonRPCClient(self.rpc_uri, timeout=timeout, method_class=_JsonRPCMethod)

    @property
    def sdk_version(self):
        """sdk version of connected device."""
        if self._sdk == 0:
            out, err, es = self._adb.command(["getprop", "ro.build.version.sdk"])
            if es:
                self._sdk = int(out.strip())
            else:
                raise UIAutomatorError("Couldn't get SDK version")
        return self._sdk

    def start(self, timeout=30):
        """Start the device side server."""
        logging.debug("AutomationServer: attempting to start")
        cf = config.get_config()
        runner = cf.uiautomator[self.source].runner
        cmd = "am instrument -w -e class com.github.uiautomator.stub.Stub " + runner
        self._adb.command("am force-stop com.github.uiautomator")
        self._uia_device_process = self._adb.spawn(cmd)
        time.sleep(1.0)
        self.forward_port()
        time.sleep(1.0)
        while not self.is_alive and timeout > 0:
            time.sleep(1.0)
            timeout -= 1
        if not self.is_alive:
            self._uia_device_process.sync_close()
            self._uia_device_process = None
            raise UIAutomatorError("RPC server not started!")
        logging.debug("AutomationServer: started")

    def stop(self):
        """Stop the rpc server."""
        if self._uia_device_process is not None:
            logging.debug("AutomationServer: stopping")
            res = None
            try:
                try:
                    res = urllib.request.urlopen(self.stop_uri)
                except RemoteDisconnected:
                    pass
            finally:
                if res is not None:
                    res.read()
                    res.close()
                self._uia_device_process.sync_close()
                self._uia_device_process = None
                self.forward_remove()

    def close(self):
        self.stop()
        if self._adb is not None:
            self._adb.close()
            self._adb = None

    def ping(self):
        return JsonRPCClient(self.rpc_uri, timeout=90).ping()

    @property
    def is_alive(self):
        """Check if the rpc server is alive."""
        try:
            return self.ping() == "pong"
        except Exception as err:  # noqa
            logging.exception_warning("AutomationServer: not alive", err)
            return False

    @property
    def stop_uri(self):
        return "http://%s:%d/stop" % (self.host, self.local_port)

    @property
    def rpc_uri(self):
        return "http://%s:%d/jsonrpc/0" % (self.host, self.local_port)

    @property
    def screenshot_uri(self):
        return "http://%s:%d/screenshot/0" % (self.host, self.local_port)

    def screenshot(self, filename=None, scale=1.0, quality=100):
        """Take a screenshot."""
        if self.sdk_version >= 18:
            req = urllib.request.Request("%s?scale=%f&quality=%f" %
                                         (self.screenshot_uri, scale, quality))
            result = urllib.request.urlopen(req, timeout=30)
            if filename:
                with open(filename, "wb") as f:
                    f.write(result.read())
                    return filename
            else:
                return result.read()
        return None


class AutomatorDevice:
    """uiautomator wrapper of android device."""

    _ORIENTATION = (  # device orientation
        (0, "natural", "n", 0),
        (1, "left", "l", 90),
        (2, "upsidedown", "u", 180),
        (3, "right", "r", 270),
    )
    _INFO_ALIASES = {"width": "displayWidth", "height": "displayHeight"}

    def __init__(
        self,
        serial,
        local_port=None,
        adb_server_host="localhost",
        adb_server_port=adb.ADB_PORT,
    ):
        self.server = AutomatorServer(
            serial=serial,
            local_port=local_port,
            adb_server_host=adb_server_host,
            adb_server_port=adb_server_port,
        )

    def __repr__(self):
        return (f"{self.__class__.__name__}({self.server.serial!r},"
                f" {self.server.local_port!r})")

    def __del__(self):
        self.close()

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server = None

    def __call__(self, **kwargs):
        return AutomatorDeviceObject(self, Selector(**kwargs))

    def __getattr__(self, attr):
        """alias of fields in info property."""
        info = self.info
        if attr in info:
            return info[attr]
        elif attr in self._INFO_ALIASES:
            return info[self._INFO_ALIASES[attr]]
        else:
            raise AttributeError("%s attribute not found!" % attr)

    @property
    def info(self):
        """Get the device info."""
        return self.server.jsonrpc.deviceInfo()

    def click(self, x, y):
        """click at arbitrary coordinates."""
        return self.server.jsonrpc.click(x, y)

    def long_click(self, x, y):
        """long click at arbitrary coordinates."""
        return self.swipe(x, y, x + 1, y + 1)

    def swipe(self, sx, sy, ex, ey, steps=100):
        return self.server.jsonrpc.swipe(sx, sy, ex, ey, steps)

    def swipePoints(self, points, steps=100):
        ppoints = []
        for p in points:
            ppoints.append(p[0])
            ppoints.append(p[1])
        return self.server.jsonrpc.swipePoints(ppoints, steps)

    def drag(self, sx, sy, ex, ey, steps=100):
        """Swipe from one point to another point."""
        return self.server.jsonrpc.drag(sx, sy, ex, ey, steps)

    def dump(self, filename=None, compressed=True, pretty=True):
        """dump device window and pull to local file."""
        content = self.server.jsonrpc.dumpWindowHierarchy(compressed, None)
        if filename:
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = xml_text.toprettyxml(indent="  ")
        return content

    def screenshot(self, filename, scale=1.0, quality=100):
        """take screenshot, Return file name to pull."""
        result = self.server.screenshot(filename, scale, quality)
        if result:
            return result

        device_file = self.server.jsonrpc.takeScreenshot("screenshot.png", scale, quality)
        return device_file if device_file else None

    def freeze_rotation(self, freeze=True):
        """freeze or unfreeze the device rotation in current status."""
        self.server.jsonrpc.freezeRotation(freeze)

    @property
    def orientation(self):
        """orienting the devie to left/right or natural.

    left/l:       rotation=90 , displayRotation=1 right/r:      rotation=270,
    displayRotation=3 natural/n:    rotation=0  , displayRotation=0
    upsidedown/u: rotation=180, displayRotation=2
    """
        return self._ORIENTATION[self.info["displayRotation"]][1]

    @orientation.setter
    def orientation(self, value):
        """setter of orientation property."""
        for values in self._ORIENTATION:
            if value in values:
                # can not set upside-down until api level 18.
                self.server.jsonrpc.setOrientation(values[1])
                break
        else:
            raise ValueError("Invalid orientation.")

    @property
    def last_traversed_text(self):
        """get last traversed text. used in webview for highlighted text."""
        return self.server.jsonrpc.getLastTraversedText()

    def clear_traversed_text(self):
        """clear the last traversed text."""
        self.server.jsonrpc.clearLastTraversedText()

    @property
    def open(self):
        """Open notification or quick settings.

    Usage: d.open.notification() d.open.quick_settings()
    """

        @param_to_property(action=["notification", "quick_settings"])
        def _open(action):
            if action == "notification":
                return self.server.jsonrpc.openNotification()
            else:
                return self.server.jsonrpc.openQuickSettings()

        return _open

    @property
    def handlers(self):
        obj = self

        class Handlers(object):

            def on(self, fn):
                if fn not in obj.server.handlers["handlers"]:
                    obj.server.handlers["handlers"].append(fn)
                obj.server.handlers["device"] = obj
                return fn

            def off(self, fn):
                if fn in obj.server.handlers["handlers"]:
                    obj.server.handlers["handlers"].remove(fn)

        return Handlers()

    @property
    def watchers(self):
        obj = self

        class Watchers(list):

            def __init__(self):
                for watcher in obj.server.jsonrpc.getWatchers():
                    self.append(watcher)

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasAnyWatcherTriggered()

            def remove(self, name=None):
                if name:
                    obj.server.jsonrpc.removeWatcher(name)
                else:
                    for name in self:
                        obj.server.jsonrpc.removeWatcher(name)

            def reset(self):
                obj.server.jsonrpc.resetWatcherTriggers()
                return self

            def run(self):
                obj.server.jsonrpc.runWatchers()
                return self

        return Watchers()

    def watcher(self, name):
        obj = self

        class Watcher(object):

            def __init__(self):
                self.__selectors = []

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasWatcherTriggered(name)

            def remove(self):
                obj.server.jsonrpc.removeWatcher(name)

            def when(self, **kwargs):
                self.__selectors.append(Selector(**kwargs))
                return self

            def click(self, **kwargs):
                obj.server.jsonrpc.registerClickUiObjectWatcher(name, self.__selectors,
                                                                Selector(**kwargs))

            @property
            def press(self):

                @param_to_property(
                    "home",
                    "back",
                    "left",
                    "right",
                    "up",
                    "down",
                    "center",
                    "search",
                    "enter",
                    "delete",
                    "del",
                    "recent",
                    "volume_up",
                    "menu",
                    "volume_down",
                    "volume_mute",
                    "camera",
                    "power",
                )
                def _press(*args):
                    obj.server.jsonrpc.registerPressKeyskWatcher(name, self.__selectors, args)

                return _press

        return Watcher()

    @property
    def press(self):
        """press key via name or key code.

    Supported key name includes: home, back, left, right, up, down, center,
    menu, search, enter, delete(or del), recent(recent apps), volume_up,
    volume_down, volume_mute, camera, power. Usage: d.press.back()  # press back
    key d.press.menu()  # press home key d.press(89)     # press keycode
    """

        @param_to_property(key=[
            "home",
            "back",
            "left",
            "right",
            "up",
            "down",
            "center",
            "menu",
            "search",
            "enter",
            "delete",
            "del",
            "recent",
            "volume_up",
            "volume_down",
            "volume_mute",
            "camera",
            "power",
        ])
        def _press(key, meta=None):
            if isinstance(key, int):
                return (self.server.jsonrpc.pressKeyCode(key, meta)
                        if meta else self.server.jsonrpc.pressKeyCode(key))  # noqa
            else:
                return self.server.jsonrpc.pressKey(str(key))

        return _press

    def wakeup(self):
        """turn on screen in case of screen off."""
        self.server.jsonrpc.wakeUp()

    def sleep(self):
        """turn off screen in case of screen on."""
        self.server.jsonrpc.sleep()

    @property
    def screen(self):
        """Turn on/off screen.

    Usage: d.screen.on() d.screen.off()

    d.screen == 'on'  # Check if the screen is on, same as 'd.screenOn'
    d.screen == 'off'  # Check if the screen is off, same as 'not d.screenOn'
    """
        devive_self = self

        class _Screen(object):

            def on(self):
                return devive_self.wakeup()

            def off(self):
                return devive_self.sleep()

            def __call__(self, action):
                if action == "on":
                    return self.on()
                elif action == "off":
                    return self.off()
                else:
                    raise AttributeError("Invalid parameter: %s" % action)

            def __eq__(self, value):
                info = devive_self.info
                if "screenOn" not in info:
                    raise EnvironmentError("Not supported on Android 4.3 and belows.")
                if value in ["on", "On", "ON"]:
                    return info["screenOn"]
                elif value in ["off", "Off", "OFF"]:
                    return not info["screenOn"]
                raise ValueError("Invalid parameter. It can only be compared with on/off.")

            def __ne__(self, value):
                return not self.__eq__(value)

        return _Screen()

    @property
    def wait(self):
        """Waits for the current application to idle or window update event occurs.

    Usage: d.wait.idle(timeout=1000) d.wait.update(timeout=1000,
    package_name="com.android.settings")
    """

        @param_to_property(action=["idle", "update"])
        def _wait(action, timeout=1000, package_name=None):
            if timeout / 1000 + 5 > 90:
                http_timeout = timeout / 1000 + 5
            else:
                http_timeout = 90
            if action == "idle":
                return self.server.jsonrpc_wrap(timeout=http_timeout).waitForIdle(timeout)
            elif action == "update":
                return self.server.jsonrpc_wrap(timeout=http_timeout).waitForWindowUpdate(
                    package_name, timeout)  # noqa

        return _wait

    def exists(self, **kwargs):
        """Check if the specified ui object by kwargs exists."""
        return self(**kwargs).exists


class AutomatorDeviceUiObject:
    """Represent a UiObject, on which user can perform actions."""

    _INFO_ALIASES = {"description": "contentDescription"}

    def __init__(self, device, selector):
        self.device = device
        self.jsonrpc = device.server.jsonrpc
        self.selector = selector

    @property
    def exists(self):
        """check if the object exists in current window."""
        return self.jsonrpc.exist(self.selector)

    def __getattr__(self, attr):
        """alias of fields in info property."""
        info = self.info
        if attr in info:
            return info[attr]
        elif attr in self._INFO_ALIASES:
            return info[self._INFO_ALIASES[attr]]
        else:
            raise AttributeError("%s attribute not found!" % attr)

    @property
    def info(self):
        """ui object info."""
        return self.jsonrpc.objInfo(self.selector)

    def set_text(self, text):
        """set the text field."""
        if text in [None, ""]:
            return self.jsonrpc.clearTextField(self.selector)  # TODO no return
        else:
            return self.jsonrpc.setText(self.selector, text)

    def clear_text(self):
        """clear text. alias for set_text(None)."""
        self.set_text(None)

    @property
    def click(self):
        """click on the ui object.

    Usage: d(text="Clock").click()  # click on the center of the ui object
    d(text="OK").click.wait(timeout=3000) # click and wait for the new window
    update d(text="John").click.topleft() # click on the topleft of the ui
    object d(text="John").click.bottomright() # click on the bottomright of the
    ui object
    """

        @param_to_property(action=["tl", "topleft", "br", "bottomright", "wait"])
        def _click(action=None, timeout=3000):
            if action is None:
                return self.jsonrpc.click(self.selector)
            elif action in ["tl", "topleft", "br", "bottomright"]:
                return self.jsonrpc.click(self.selector, action)
            else:
                return self.jsonrpc.clickAndWaitForNewWindow(self.selector, timeout)

        return _click

    @property
    def long_click(self):
        """Perform a long click action on the object.

    Usage: d(text="Image").long_click()  # long click on the center of the ui
    object d(text="Image").long_click.topleft()  # long click on the topleft of
    the ui object d(text="Image").long_click.bottomright()  # long click on the
    topleft of the ui object
    """

        @param_to_property(corner=["tl", "topleft", "br", "bottomright"])
        def _long_click(corner=None):
            info = self.info
            if info["longClickable"]:
                if corner:
                    return self.jsonrpc.longClick(self.selector, corner)
                else:
                    return self.jsonrpc.longClick(self.selector)
            else:
                bounds = info.get("visibleBounds") or info.get("bounds")
                if corner in ["tl", "topleft"]:
                    x = (5 * bounds["left"] + bounds["right"]) / 6
                    y = (5 * bounds["top"] + bounds["bottom"]) / 6
                elif corner in ["br", "bottomright"]:
                    x = (bounds["left"] + 5 * bounds["right"]) / 6
                    y = (bounds["top"] + 5 * bounds["bottom"]) / 6
                else:
                    x = (bounds["left"] + bounds["right"]) / 2
                    y = (bounds["top"] + bounds["bottom"]) / 2
                return self.device.long_click(x, y)

        return _long_click

    @property
    def drag(self):
        """Drag the ui object to other point or ui object.

    Usage: d(text="Clock").drag.to(x=100, y=100)  # drag to point (x,y)
    d(text="Clock").drag.to(text="Remove") # drag to another object
    """

        def to(obj, *args, **kwargs):
            if len(args) >= 2 or "x" in kwargs or "y" in kwargs:
                drag_to = lambda x, y, steps=100: self.jsonrpc.dragTo(self.selector, x, y, steps
                                                                     )  # noqa
            else:
                drag_to = lambda steps=100, **kwargs: self.jsonrpc.dragTo(
                    self.selector, Selector(**kwargs), steps)  # noqa
            return drag_to(*args, **kwargs)

        return type("Drag", (object,), {"to": to})()

    def gesture(self, start1, start2, *args, **kwargs):
        """perform two point gesture.

    Usage: d().gesture(startPoint1, startPoint2).to(endPoint1, endPoint2, steps)
    d().gesture(startPoint1, startPoint2, endPoint1, endPoint2, steps)
    """

        def to(obj_self, end1, end2, steps=100):
            ctp = lambda pt: point(*pt) if isinstance(pt, tuple
                                                     ) else pt  # noqa convert tuple to point
            s1, s2, e1, e2 = ctp(start1), ctp(start2), ctp(end1), ctp(end2)
            return self.jsonrpc.gesture(self.selector, s1, s2, e1, e2, steps)

        obj = type("Gesture", (object,), {"to": to})()
        return obj if len(args) == 0 else to(None, *args, **kwargs)

    def gestureM(self, start1, start2, start3, *args, **kwargs):
        """perform 3 point gesture.

    Usage:
    d().gestureM((100,200),(100,300),(100,400),(100,400),(100,400),(100,400))
    d().gestureM((100,200),(100,300),(100,400)).to((100,400),(100,400),(100,400))
    """

        def to(obj_self, end1, end2, end3, steps=100):
            ctp = lambda pt: point(*pt) if type(pt) == tuple else pt  # noqa convert tuple to point
            s1, s2, s3, e1, e2, e3 = (
                ctp(start1),
                ctp(start2),
                ctp(start3),
                ctp(end1),
                ctp(end2),
                ctp(end3),
            )  # noqa
            return self.jsonrpc.gesture(self.selector, s1, s2, s3, e1, e2, e3, steps)

        obj = type("Gesture", (object,), {"to": to})()
        return obj if len(args) == 0 else to(None, *args, **kwargs)

    @property
    def pinch(self):
        """Perform two point gesture from edge to center(in) or center to edge(out).

    Usages: d().pinch.In(percent=100, steps=10) d().pinch.Out(percent=100,
    steps=100)
    """

        @param_to_property(in_or_out=["In", "Out"])
        def _pinch(in_or_out="Out", percent=100, steps=50):
            if in_or_out in ["Out", "out"]:
                return self.jsonrpc.pinchOut(self.selector, percent, steps)
            elif in_or_out in ["In", "in"]:
                return self.jsonrpc.pinchIn(self.selector, percent, steps)

        return _pinch

    @property
    def swipe(self):
        """Perform swipe action.

    if device platform greater than API 18, percent can be used and value
    between 0 and 1

    Usages:
    d().swipe.right()
    d().swipe.left(steps=10)
    d().swipe.up(steps=10)
    d().swipe.down()
    d().swipe("right", steps=20)
    d().swipe("right", steps=20, percent=0.5)
    """

        @param_to_property(direction=["up", "down", "right", "left"])
        def _swipe(direction="left", steps=10, percent=1):
            if percent == 1:
                return self.jsonrpc.swipe(self.selector, direction, steps)
            else:
                return self.jsonrpc.swipe(self.selector, direction, percent, steps)

        return _swipe

    @property
    def wait(self):
        """Wait until the ui object gone or exist.

    Usage: d(text="Clock").wait.gone()  # wait until it's gone.
    d(text="Settings").wait.exists() # wait until it appears.
    """

        @param_to_property(action=["exists", "gone"])
        def _wait(action, timeout=3000):
            if timeout / 1000 + 5 > 90:
                http_timeout = timeout / 1000 + 5
            else:
                http_timeout = 90
            method = (self.device.server.jsonrpc_wrap(timeout=http_timeout).waitUntilGone
                      if action == "gone" else self.device.server.jsonrpc_wrap(
                          timeout=http_timeout).waitForExists)  # noqa
            return method(self.selector, timeout)

        return _wait


class AutomatorDeviceNamedUiObject(AutomatorDeviceUiObject):

    def __init__(self, device, name):
        super(AutomatorDeviceNamedUiObject, self).__init__(device, name)

    def child(self, **kwargs):
        return AutomatorDeviceNamedUiObject(
            self.device, self.jsonrpc.getChild(self.selector, Selector(**kwargs)))

    def sibling(self, **kwargs):
        return AutomatorDeviceNamedUiObject(
            self.device,
            self.jsonrpc.getFromParent(self.selector, Selector(**kwargs)),
        )


class AutomatorDeviceObject(AutomatorDeviceUiObject):
    """Represent a generic UiObject/UiScrollable/UiCollection,

  on which user can perform actions, such as click, set text
  """

    def __init__(self, device, selector):
        super(AutomatorDeviceObject, self).__init__(device, selector)

    def child(self, **kwargs):
        """set childSelector."""
        return AutomatorDeviceObject(self.device, self.selector.clone().child(**kwargs))

    def sibling(self, **kwargs):
        """set fromParent selector."""
        return AutomatorDeviceObject(self.device, self.selector.clone().sibling(**kwargs))

    child_selector, from_parent = child, sibling

    def child_by_text(self, txt, **kwargs):
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs), txt,
                                            allow_scroll_search)
        else:
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs), txt)
        return AutomatorDeviceNamedUiObject(self.device, name)

    def child_by_description(self, txt, **kwargs):
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByDescription(self.selector, Selector(**kwargs), txt,
                                                   allow_scroll_search)
        else:
            name = self.jsonrpc.childByDescription(self.selector, Selector(**kwargs), txt)
        return AutomatorDeviceNamedUiObject(self.device, name)

    def child_by_instance(self, inst, **kwargs):
        return AutomatorDeviceNamedUiObject(
            self.device,
            self.jsonrpc.childByInstance(self.selector, Selector(**kwargs), inst),
        )

    @property
    def count(self):
        return self.jsonrpc.count(self.selector)

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        count = self.count
        if index >= count:
            raise IndexError()
        elif count == 1:
            return self
        else:
            selector = self.selector.clone()
            selector["instance"] = index
            return AutomatorDeviceObject(self.device, selector)

    def __iter__(self):
        obj, length = self, self.count

        class Iter(object):

            def __init__(self):
                self.index = -1

            def __next__(self):
                self.index += 1
                if self.index < length:
                    return obj[self.index]
                else:
                    raise StopIteration()

        return Iter()

    def right(self, **kwargs):

        def onrightof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["left"] - rect1["right"] if top < bottom else -1

        return self.__view_beside(onrightof, **kwargs)

    def left(self, **kwargs):

        def onleftof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["left"] - rect2["right"] if top < bottom else -1

        return self.__view_beside(onleftof, **kwargs)

    def up(self, **kwargs):

        def above(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["top"] - rect2["bottom"] if left < right else -1

        return self.__view_beside(above, **kwargs)

    def down(self, **kwargs):

        def under(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["top"] - rect1["bottom"] if left < right else -1

        return self.__view_beside(under, **kwargs)

    def __view_beside(self, onsideof, **kwargs):
        bounds = self.info["bounds"]
        min_dist, found = -1, None
        for ui in AutomatorDeviceObject(self.device, Selector(**kwargs)):
            dist = onsideof(bounds, ui.info["bounds"])
            if dist >= 0 and (min_dist < 0 or dist < min_dist):
                min_dist, found = dist, ui
        return found

    @property
    def fling(self):
        """Perform fling action.

    Usage: d().fling()  # default vertically, forward d().fling.horiz.forward()
    d().fling.vert.backward() d().fling.toBeginning(max_swipes=100) # vertically
    d().fling.horiz.toEnd()
    """

        @param_to_property(
            dimention=[
                "vert",
                "vertically",
                "vertical",
                "horiz",
                "horizental",
                "horizentally",
            ],
            action=["forward", "backward", "toBeginning", "toEnd"],
        )
        def _fling(dimention="vert", action="forward", max_swipes=1000):
            vertical = dimention in ["vert", "vertically", "vertical"]
            if action == "forward":
                return self.jsonrpc.flingForward(self.selector, vertical)
            elif action == "backward":
                return self.jsonrpc.flingBackward(self.selector, vertical)
            elif action == "toBeginning":
                return self.jsonrpc.flingToBeginning(self.selector, vertical, max_swipes)
            elif action == "toEnd":
                return self.jsonrpc.flingToEnd(self.selector, vertical, max_swipes)

        return _fling

    @property
    def scroll(self):
        """Perfrom scroll action.

    Usage: d().scroll(steps=50) # default vertically and forward
    d().scroll.horiz.forward(steps=100) d().scroll.vert.backward(steps=100)
    d().scroll.horiz.toBeginning(steps=100, max_swipes=100)
    d().scroll.vert.toEnd(steps=100) d().scroll.horiz.to(text="Clock")
    """

        def __scroll(vertical, forward, steps=100):
            method = (self.jsonrpc.scrollForward if forward else self.jsonrpc.scrollBackward)
            return method(self.selector, vertical, steps)

        def __scroll_to_beginning(vertical, steps=100, max_swipes=1000):
            return self.jsonrpc.scrollToBeginning(self.selector, vertical, max_swipes, steps)

        def __scroll_to_end(vertical, steps=100, max_swipes=1000):
            return self.jsonrpc.scrollToEnd(self.selector, vertical, max_swipes, steps)

        def __scroll_to(vertical, **kwargs):
            return self.jsonrpc.scrollTo(self.selector, Selector(**kwargs), vertical)

        @param_to_property(
            dimention=[
                "vert",
                "vertically",
                "vertical",
                "horiz",
                "horizental",
                "horizentally",
            ],
            action=["forward", "backward", "toBeginning", "toEnd", "to"],
        )
        def _scroll(dimention="vert", action="forward", **kwargs):
            vertical = dimention in ["vert", "vertically", "vertical"]
            if action in ["forward", "backward"]:
                return __scroll(vertical, action == "forward", **kwargs)
            elif action == "toBeginning":
                return __scroll_to_beginning(vertical, **kwargs)
            elif action == "toEnd":
                return __scroll_to_end(vertical, **kwargs)
            elif action == "to":
                return __scroll_to(vertical, **kwargs)

        return _scroll
