# -*- coding: utf-8 -*-
"""Reads local Codex session JSONL rate_limits and merges with live UI percentages."""

import glob
import json
import os
from datetime import datetime, timedelta

MAX_TAIL_BYTES = 2 * 1024 * 1024
TAIL_DAYS = 3


def sessions_root():
    base = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(base, "sessions")


def _recent_files(days=TAIL_DAYS):
    root = sessions_root()
    if not os.path.isdir(root):
        return []
    files = []
    today = datetime.now()
    for offset in range(days + 1):
        day = today - timedelta(days=offset)
        pattern = os.path.join(root, day.strftime("%Y"), day.strftime("%m"), day.strftime("%d"), "*.jsonl")
        files.extend(glob.glob(pattern))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def _find_rate_limits(node):
    if isinstance(node, dict):
        if "rate_limits" in node and isinstance(node["rate_limits"], dict):
            return node["rate_limits"]
        for value in node.values():
            found = _find_rate_limits(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_rate_limits(value)
            if found is not None:
                return found
    return None


def _read_tail_lines(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > MAX_TAIL_BYTES:
            f.seek(size - MAX_TAIL_BYTES)
        raw = f.read()
    text = raw.decode("utf-8", "replace")
    lines = text.split("\n")
    return lines[1:] if size > MAX_TAIL_BYTES else lines


def _window(raw):
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percent")
    resets_at = raw.get("resets_at")
    minutes = raw.get("window_minutes")
    remaining = None
    if isinstance(used, (int, float)):
        remaining = float(int(max(0.0, min(100.0, 100.0 - float(used)))))
    reset_dt = None
    if isinstance(resets_at, (int, float)):
        reset_dt = datetime.fromtimestamp(resets_at).astimezone()
    return {
        "used_percent": float(used) if isinstance(used, (int, float)) else None,
        "remaining_percent": remaining,
        "window_minutes": int(minutes) if isinstance(minutes, (int, float)) else None,
        "resets_at": reset_dt.isoformat(timespec="seconds") if reset_dt else None,
    }


def parse_record(payload, observed_at=None):
    if not isinstance(payload, dict):
        return None
    five = _window(payload.get("primary"))
    week = _window(payload.get("secondary"))
    if five is None and week is None:
        return None
    credits = payload.get("credits") or {}
    return {
        "ok": True,
        "plan_type": payload.get("plan_type"),
        "limit_id": payload.get("limit_id"),
        "five_hour": five,
        "weekly": week,
        "credits_balance": credits.get("balance"),
        "observed_at": observed_at,
    }


def read_limits(snap=None, state=None):
    disk_res = None
    for path in _recent_files()[:8]:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
            for line in reversed(_read_tail_lines(path)):
                if "rate_limits" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                found = _find_rate_limits(obj)
                if found is None:
                    continue
                result = parse_record(found, mtime.isoformat(timespec="seconds"))
                if result:
                    result["source"] = "Codex Log"
                    disk_res = result
                    break
            if disk_res:
                break
        except OSError:
            continue

    if disk_res is None:
        disk_res = {
            "ok": True,
            "five_hour": {"remaining_percent": None, "resets_at": None},
            "weekly": {"remaining_percent": None, "resets_at": None},
            "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "Live UI",
        }

    if snap is not None:
        if state == "quota_exhausted":
            disk_res["five_hour"]["remaining_percent"] = 0.0
            disk_res["source"] = "Live UI Banner"
            disk_res["observed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if getattr(snap, "live_5h_pct", None) is not None:
            disk_res["five_hour"]["remaining_percent"] = snap.live_5h_pct
            disk_res["source"] = "Live UI Popup"
            disk_res["observed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if getattr(snap, "live_weekly_pct", None) is not None:
            disk_res["weekly"]["remaining_percent"] = snap.live_weekly_pct
            disk_res["source"] = "Live UI Popup"
            disk_res["observed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    return disk_res
