# -*- coding: utf-8 -*-
"""System tray icon and English menu."""

import threading
import pystray
from PIL import Image, ImageDraw


def _image(color=(11, 87, 208, 255)):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill=color)
    draw.ellipse((26, 18, 38, 30), fill=(255, 255, 255, 235))
    return img


class Tray:
    def __init__(self, on_show, on_act, on_quit, logbook=None, tooltip="ChatGPT Auto Resume"):
        self.log = logbook
        self._on_show = on_show
        self._on_act = on_act
        self._on_quit = on_quit
        self._icon = None
        self._thread = None
        self._tooltip = tooltip

    def _build(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show Dashboard", self._show, default=True),
            pystray.MenuItem("Send 'Continue' Now", self._act),
            pystray.MenuItem("Quit", self._quit),
        )
        self._icon = pystray.Icon("AutoResume", _image(), self._tooltip, menu)

    def start(self):
        try:
            self._build()
            self._thread = threading.Thread(target=self._icon.run, daemon=True, name="tray")
            self._thread.start()
            return True
        except Exception as exc:
            if self.log:
                self.log.write("warn", "tray_start_fail", detail=repr(exc))
            return False

    def stop(self):
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:
            pass

    def set_tooltip(self, text):
        try:
            if self._icon is not None:
                self._icon.title = text[:120]
        except Exception:
            pass

    def _show(self, icon=None, item=None):
        self._on_show()

    def _act(self, icon=None, item=None):
        self._on_act()

    def _quit(self, icon=None, item=None):
        self._on_quit()
