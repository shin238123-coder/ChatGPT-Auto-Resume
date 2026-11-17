# -*- coding: utf-8 -*-
"""Win32 window discovery and focus control for ChatGPT.exe."""

import ctypes
import time
from ctypes import wintypes

import psutil
import uiautomation as auto

from .constants import PROCESS_NAME, WINDOW_CLASS

_user32 = ctypes.windll.user32
SW_RESTORE = 9
VK_MENU = 0x12
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_cached_hwnd = 0


def chatgpt_pids():
    pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info["name"] or "").lower() == PROCESS_NAME.lower():
                pids.add(proc.info["pid"])
        except Exception:
            continue
    return pids


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd):
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_rect(hwnd):
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (0, 0, 0, 0)
    return (rect.left, rect.top, rect.right, rect.bottom)


def _rect_area(hwnd):
    l, t, r, b = get_window_rect(hwnd)
    return max(0, r - l) * max(0, b - t)


def find_hwnd():
    global _cached_hwnd
    pids = chatgpt_pids()
    if not pids:
        _cached_hwnd = 0
        return 0
    if _cached_hwnd and _user32.IsWindow(_cached_hwnd):
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(_cached_hwnd, ctypes.byref(pid))
        if pid.value in pids:
            return _cached_hwnd

    found = []

    def callback(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if _class_name(hwnd) != WINDOW_CLASS:
            return True
        if not _title(hwnd):
            return True
        found.append(hwnd)
        return True

    _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    if not found:
        _cached_hwnd = 0
        return 0
    best = max(found, key=_rect_area)
    _cached_hwnd = best
    return best


def find_window():
    hwnd = find_hwnd()
    if not hwnd:
        return None
    try:
        return auto.ControlFromHandle(hwnd)
    except Exception:
        return None


def is_foreground(hwnd):
    return _user32.GetForegroundWindow() == hwnd


def force_foreground(hwnd):
    try:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.3)
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        if is_foreground(hwnd):
            return True
        _user32.keybd_event(VK_MENU, 0, 0, 0)
        _user32.keybd_event(VK_MENU, 0, 2, 0)
        time.sleep(0.1)
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        return is_foreground(hwnd)
    except Exception:
        return False


def focus_window(hwnd):
    return force_foreground(hwnd)
