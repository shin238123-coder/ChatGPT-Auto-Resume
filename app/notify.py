# -*- coding: utf-8 -*-
"""Windows Shell_NotifyIcon balloon notifications (100% English)."""

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_ICON, NIF_TIP, NIF_INFO = 0x02, 0x04, 0x10
NIIF_INFO, NIIF_WARNING, NIIF_ERROR = 0x01, 0x02, 0x03
IDI_APPLICATION = 32512


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class Notifier:
    def __init__(self, hwnd, logbook=None):
        self.hwnd = hwnd
        self.log = logbook
        self._added = False

    def _data(self):
        data = NOTIFYICONDATA()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        data.hWnd = self.hwnd
        data.uID = 1
        return data

    def _ensure_icon(self):
        if self._added:
            return True
        data = self._data()
        data.uFlags = NIF_ICON | NIF_TIP
        data.hIcon = _user32.LoadIconW(None, IDI_APPLICATION)
        data.szTip = "ChatGPT Auto Resume"
        ok = bool(_shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)))
        self._added = ok
        return ok

    def notify(self, title, text, level="info"):
        flag = {"info": NIIF_INFO, "warn": NIIF_WARNING, "error": NIIF_ERROR}.get(level, NIIF_INFO)
        try:
            if not self._ensure_icon():
                raise RuntimeError("Tray icon registration failed")
            data = self._data()
            data.uFlags = NIF_INFO
            data.szInfoTitle = title[:63]
            data.szInfo = text[:255]
            data.dwInfoFlags = flag
            ok = bool(_shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data)))
            if not ok:
                raise RuntimeError("Balloon notification failed")
            return True
        except Exception as exc:
            if self.log:
                self.log.write("warn", "notify_fail", detail=str(exc), title=title)
            self._flash()
            return False

    def _flash(self):
        try:
            _user32.FlashWindow(self.hwnd, True)
        except Exception:
            pass
