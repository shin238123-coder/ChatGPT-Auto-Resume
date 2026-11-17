# -*- coding: utf-8 -*-
"""DPI-Adaptive & Geometry-Aware UIA Reader for ChatGPT Desktop App."""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import uiautomation as auto

from . import constants as C
from . import planner
from .discovery import find_window, is_foreground, get_window_rect

MAX_NODES = 4500
DEPTH_CAP = 36

NAMED_KINDS = {
    "ButtonControl", "TextControl", "EditControl", "DocumentControl",
    "ImageControl", "StatusBarControl", "ListItemControl", "TreeItemControl",
    "TabItemControl", "HyperlinkControl"
}

RESET_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})")
RESET_AMPM_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\b", re.IGNORECASE)
RESET_24H_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

RESET_HINT_WORDS = (
    "retry", "resets", "reset at", "resets on", "try again",
    "rate limit", "usage limit", "out of codex"
)

NON_CHAT_NAMES = {
    "chatgpt", "new chat", "pinned", "choose models for chatgpt work",
    "projects", "recents", "chatgpt workspace", "file", "edit", "view",
    "help", "upgrade", "reset usage", "add credits", "manage usage",
    "work with chatgpt", "import", "+ add column", "find people - apollo",
    "minimize", "maximize", "close", "restore", "back", "forward",
    "open sidebar", "close sidebar", "toggle sidebar", "search", "notifications", "images", "scheduled", "library", "plugins", "explore", "sites", "usage", "open profile menu", "home", "more", "apps", "codex", "settings"
}

DEFAULT_WINDOW_MINUTES = 300
PROJECT_RE = re.compile(r"^Project:\s*(.+)$", re.IGNORECASE)
CONTEXT_RE = re.compile(r"^Context(?:\s+used)?:\s*(\d+)%$", re.IGNORECASE)
PCT_LEFT_RE = re.compile(r"(\d{1,3})%\s*left", re.IGNORECASE)


@dataclass
class Item:
    kind: str
    name: str = ""
    cls: str = ""
    enabled: bool = True
    depth: int = 0
    value: str = ""
    off: bool = False
    rx: int = -1
    ry: int = -1


@dataclass
class Snap:
    ok: bool = False
    error: str = ""
    pid: int = 0
    hwnd: int = 0
    foreground: bool = False
    project: str = ""
    thread: str = ""
    model: str = ""
    permission: str = ""
    context_pct: int = -1
    stop_present: bool = False
    approval: list = field(default_factory=list)
    waiting_text: str = ""
    quota_msgs: list = field(default_factory=list)
    reset_clock: str = ""
    reset_at: object = None
    goal_status: str = ""
    goal_objective: str = ""
    goal_actions: list = field(default_factory=list)
    composer_present: bool = False
    composer_empty: bool = True
    send_present: bool = False
    send_enabled: bool = False
    live_5h_pct: object = None
    live_weekly_pct: object = None
    sidebar_threads: list = field(default_factory=list)
    read_ms: int = 0


def _walk(ctrl, depth, out, win_left, win_top):
    if depth > DEPTH_CAP or len(out) >= MAX_NODES:
        return
    try:
        kind = ctrl.ControlTypeName
    except Exception:
        return
    item = Item(kind=kind, depth=depth)
    if kind in NAMED_KINDS:
        try:
            item.name = (ctrl.Name or "").strip()
        except Exception:
            item.name = ""
    if kind in ("ButtonControl", "EditControl", "ListItemControl"):
        try:
            item.cls = ctrl.ClassName or ""
        except Exception:
            item.cls = ""
    if kind == "ButtonControl":
        try:
            item.enabled = bool(ctrl.IsEnabled)
        except Exception:
            item.enabled = True
    if kind == "EditControl":
        try:
            vp = ctrl.GetPattern(auto.PatternId.ValuePattern)
            item.value = (vp.Value if vp else "") or ""
        except Exception:
            item.value = ""
    if item.name and kind in ("ButtonControl", "ListItemControl", "TreeItemControl", "TextControl", "DocumentControl", "HyperlinkControl"):
        try:
            item.off = bool(ctrl.IsOffscreen)
        except Exception:
            item.off = False
        if not item.off and kind in ("ButtonControl", "ListItemControl", "TreeItemControl", "HyperlinkControl", "TextControl"):
            try:
                r = ctrl.BoundingRectangle
                if r and r.width() > 0:
                    item.rx = r.left - win_left
                    item.ry = r.top - win_top
            except Exception:
                pass
    out.append(item)
    if len(out) >= MAX_NODES:
        return
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for ch in children:
        _walk(ch, depth + 1, out, win_left, win_top)


def _pause_ms(t0):
    return int((time.time() - t0) * 1000)


def _is_valid_chat_title(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 95:
        return False
    low = name.strip().lower()
    if low in NON_CHAT_NAMES:
        return False
    for bad_prefix in (
        "you've hit", "you're out of", "your rate limit", "upgrade",
        "5-hour limit", "weekly limit", "credits", "used the browser",
        "http://", "https://", "app.apollo.io", "work with chatgpt"
    ):
        if low.startswith(bad_prefix) or bad_prefix in low:
            return False
    if low.endswith("% left") or low.endswith("credits"):
        return False
    return True


def read(win=None):
    t0 = time.time()
    snap = Snap()
    try:
        if win is None:
            import ctypes
            from .discovery import find_hwnd
            hwnd_chk = find_hwnd()
            if hwnd_chk and ctypes.windll.user32.IsIconic(hwnd_chk):
                ctypes.windll.user32.ShowWindow(hwnd_chk, 9)
                time.sleep(0.25)
            win = find_window()
        if win is None:
            snap.error = "ChatGPT client not running"
            snap.read_ms = _pause_ms(t0)
            return snap
        snap.pid = win.ProcessId
        snap.hwnd = win.NativeWindowHandle
        snap.foreground = is_foreground(snap.hwnd)
        win_left, win_top, win_right, win_bottom = get_window_rect(snap.hwnd)
        win_width = max(800, win_right - win_left)
    except Exception as exc:
        snap.error = "Failed to read window: " + repr(exc)
        snap.read_ms = _pause_ms(t0)
        return snap

    items = []
    try:
        _walk(win, 0, items, win_left, win_top)
    except Exception as exc:
        snap.error = "Failed to walk UIA tree: " + repr(exc)
        snap.read_ms = _pause_ms(t0)
        return snap

    sidebar_max_x = min(400, max(270, int(win_width * 0.25)))

    composer_value = ""
    sidebar_list = []
    sidebar_set = set()
    header_candidates = []
    doc_candidates = []

    for it in items:
        if not it.name or it.off:
            continue
        if it.kind in ("ListItemControl", "TreeItemControl", "ButtonControl", "HyperlinkControl"):
            if 68 <= it.rx < sidebar_max_x and it.ry > 150:
                if _is_valid_chat_title(it.name) and it.name not in sidebar_set:
                    sidebar_list.append(it.name)
                    sidebar_set.add(it.name)

    snap.sidebar_threads = sidebar_list

    for idx, it in enumerate(items):
        name = it.name
        if it.kind == "EditControl" and C.COMPOSER_CLASS_MARK in it.cls:
            composer_value = it.value
        if not name:
            continue

        low = name.lower()

        if not it.off and it.rx >= (sidebar_max_x - 30) and 25 <= it.ry <= 165:
            if it.kind in ("ButtonControl", "TextControl") and _is_valid_chat_title(name):
                priority = 0 if name in sidebar_set else 1
                header_candidates.append((priority, it.ry, name))

        if it.kind == "DocumentControl" and not it.off and _is_valid_chat_title(name):
            doc_candidates.append(name)

        m = PROJECT_RE.match(name)
        if m:
            snap.project = m.group(1).strip()

        m = CONTEXT_RE.match(name)
        if m:
            snap.context_pct = int(m.group(1))

        if "5-hour limit" in low:
            m_inline = PCT_LEFT_RE.search(name)
            if m_inline:
                snap.live_5h_pct = float(m_inline.group(1))
            else:
                for nxt in items[idx + 1: idx + 5]:
                    m_nxt = PCT_LEFT_RE.search(nxt.name or "")
                    if m_nxt:
                        snap.live_5h_pct = float(m_nxt.group(1))
                        break

        if "weekly limit" in low:
            m_inline = PCT_LEFT_RE.search(name)
            if m_inline:
                snap.live_weekly_pct = float(m_inline.group(1))
            else:
                for nxt in items[idx + 1: idx + 5]:
                    m_nxt = PCT_LEFT_RE.search(nxt.name or "")
                    if m_nxt:
                        snap.live_weekly_pct = float(m_nxt.group(1))
                        break

        if it.kind == "ButtonControl" and name in C.STOP_LABELS:
            snap.stop_present = True

        if it.kind == "ButtonControl" and name in C.APPROVAL_LABELS:
            if name not in snap.approval:
                snap.approval.append(name)

        if it.kind == "TextControl" and planner.is_waiting_label(name, it.off):
            snap.waiting_text = name

        if planner.is_quota_text(name, it.off):
            if name not in snap.quota_msgs:
                snap.quota_msgs.append(name)

        if name in C.GOAL_LABELS:
            snap.goal_status = name

        if it.kind == "ButtonControl" and name in (C.GOAL_RESUME, C.GOAL_PAUSE, C.GOAL_CLEAR, C.GOAL_EDIT):
            if name not in snap.goal_actions:
                snap.goal_actions.append(name)

        if it.kind == "EditControl" and C.COMPOSER_CLASS_MARK in it.cls:
            snap.composer_present = True
            text = composer_value.rstrip("\r\n").strip()
            snap.composer_empty = (text == "" or text == name or text.lower() == "continue")

        if it.kind == "ButtonControl" and name in C.SEND_LABELS:
            snap.send_present = True
            snap.send_enabled = it.enabled and "opacity-50" not in it.cls

    if header_candidates:
        header_candidates.sort(key=lambda x: (x[0], x[1]))
        snap.thread = header_candidates[0][2]
    elif doc_candidates:
        for dc in doc_candidates:
            if dc in sidebar_set:
                snap.thread = dc
                break
        if not snap.thread:
            snap.thread = doc_candidates[0]

    now = _now()
    best_reset = None
    best_clock = ""
    for msg in snap.quota_msgs:
        reset_at, clock = parse_reset_time(msg, now)
        if reset_at and (best_reset is None or reset_at > best_reset):
            best_reset = reset_at
            best_clock = clock

    if best_reset:
        snap.reset_at = best_reset
        snap.reset_clock = best_clock
        if snap.live_5h_pct is None:
            snap.live_5h_pct = 0.0

    snap.ok = True
    snap.read_ms = _pause_ms(t0)
    return snap


def _now():
    return datetime.now().astimezone()


def parse_reset_time(text, now):
    if not text:
        return None, ""
    lowered = text.lower()
    if not any(word in lowered for word in RESET_HINT_WORDS):
        return None, ""

    m_iso = RESET_ISO_RE.search(text)
    if m_iso:
        year, month, day, hour, minute = (int(m_iso.group(i)) for i in range(1, 6))
        try:
            target = now.replace(year=year, month=month, day=day, hour=hour,
                                 minute=minute, second=0, microsecond=0)
            return target, m_iso.group(0).strip()
        except ValueError:
            return None, ""

    m_ampm = RESET_AMPM_RE.search(text)
    if m_ampm:
        hour = int(m_ampm.group(1))
        minute = int(m_ampm.group(2))
        ampm = m_ampm.group(3).upper()
        if ampm == "PM" and hour < 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Handle explicit 'tomorrow' or 'Nov 15' multi-day rate limits
        m_date = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})\b", text, re.I)
        m_date_rev = re.search(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", text, re.I)
        if "tomorrow" in lowered:
            target += timedelta(days=1)
        elif m_date:
            months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mon = months[m_date.group(1)[:3].lower()]
            day_num = int(m_date.group(2))
            try:
                target = target.replace(month=mon, day=day_num)
            except ValueError:
                pass
        elif m_date_rev:
            months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mon = months[m_date_rev.group(2)[:3].lower()]
            day_num = int(m_date_rev.group(1))
            try:
                target = target.replace(month=mon, day=day_num)
            except ValueError:
                pass
        elif (now - target).total_seconds() > 14400:
            target += timedelta(days=1)
        return target, target.strftime("%H:%M")

    m_24 = RESET_24H_RE.search(text)
    if m_24:
        hour, minute = int(m_24.group(1)), int(m_24.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if (now - target).total_seconds() > 14400:
                while target <= now:
                    target += timedelta(minutes=DEFAULT_WINDOW_MINUTES)
            return target, target.strftime("%H:%M")

    return None, ""
