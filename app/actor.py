# -*- coding: utf-8 -*-
"""UI actions: DPI-aware sidebar thread discovery, switching, and Continuation sending."""

import time
import uiautomation as auto

from . import constants as C
from . import discovery, planner, reader

MAX_WAIT_THREAD = 10.0


def _buttons(win):
    out = []
    stack = [win]
    while stack:
        c = stack.pop()
        try:
            if c.ControlTypeName == "ButtonControl":
                out.append(c)
                continue
            stack.extend(reversed(c.GetChildren()))
        except Exception:
            continue
    return out


def list_conversations():
    """Returns all valid conversation items from the ChatGPT left sidebar."""
    with auto.UIAutomationInitializerInThread():
        snap = reader.read()
        if snap and snap.sidebar_threads:
            return [{"project": "Workspace", "conversations": snap.sidebar_threads}]
        return []


def find_button(win, name):
    target = (name or "").strip().lower()
    for c in _buttons(win):
        try:
            if (c.Name or "").strip().lower() == target:
                return c
        except Exception:
            continue
    return None


def _invoke(ctrl):
    try:
        if not ctrl.IsEnabled:
            return ""
    except Exception:
        pass
    try:
        ctrl.GetInvokePattern().Invoke()
        return "invoke"
    except Exception:
        pass
    try:
        ctrl.GetSelectionItemPattern().Select()
        return "select"
    except Exception:
        pass
    try:
        ctrl.Click(simulateMove=False)
        return "click"
    except Exception:
        pass
    try:
        x, y = ctrl.GetClickablePoint()
        auto.Click(x, y)
        return "mouse"
    except Exception:
        return ""


def invoke_resume_goal(win):
    for name in (C.GOAL_RESUME, C.GOAL_RESUME_CONFIRM, "Resume", "Continue", "Try again"):
        ctrl = find_button(win, name)
        if ctrl is not None:
            how = _invoke(ctrl)
            if how:
                return how
    for ctrl in _buttons(win):
        try:
            name = (ctrl.Name or "").lower()
        except Exception:
            continue
        if len(name) <= 24 and ("resume" in name or "continue" in name):
            how = _invoke(ctrl)
            if how:
                return how
    return ""


def click_sidebar_thread(win, title):
    """Clicks a conversation specifically inside the left sidebar."""
    target = (title or "").strip().lower()
    hwnd = discovery.find_hwnd()
    win_left, _, win_right, _ = discovery.get_window_rect(hwnd) if hwnd else (0, 0, 1200, 800)
    sidebar_max_x = min(400, max(270, int(max(800, win_right - win_left) * 0.25)))
    stack = [win]
    count = 0
    candidates = []
    while stack and count < 4500:
        c = stack.pop()
        count += 1
        try:
            kind = c.ControlTypeName
            if kind in ("ListItemControl", "TreeItemControl", "ButtonControl", "HyperlinkControl", "TextControl"):
                nm = (c.Name or "").strip()
                if nm.lower() == target and not c.IsOffscreen:
                    r = c.BoundingRectangle
                    rx = (r.left - win_left) if r else 100
                    prio = 0 if rx < sidebar_max_x else 1
                    candidates.append((prio, c))
            stack.extend(reversed(c.GetChildren()))
        except Exception:
            continue
    candidates.sort(key=lambda x: x[0])
    for _, ctrl in candidates:
        if _invoke(ctrl):
            return True
    return False


def click_button(win, name):
    ctrl = find_button(win, name)
    if ctrl is not None and _invoke(ctrl):
        return True
    return click_sidebar_thread(win, name)


def _composer(win):
    stack = [win]
    while stack:
        c = stack.pop()
        try:
            if c.ControlTypeName == "EditControl" and C.COMPOSER_CLASS_MARK in (c.ClassName or ""):
                return c
            stack.extend(reversed(c.GetChildren()))
        except Exception:
            continue
    return None


def switch_to_thread(title, timeout=MAX_WAIT_THREAD):
    with auto.UIAutomationInitializerInThread():
        hwnd = discovery.find_hwnd()
        if hwnd:
            discovery.force_foreground(hwnd)
        win = discovery.find_window()
        if win is None:
            return False, "ChatGPT client not running"
        if not click_sidebar_thread(win, title):
            return False, "Thread not found in sidebar: " + title
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.4)
            snap = reader.read()
            if snap.thread == title:
                return True, ""
        return True, ""


def set_composer_text(text):
    """Focuses the ChatGPT input box, types 'Continue' without touching the clipboard, and verifies."""
    win = discovery.find_window()
    if win is None:
        return False, "ChatGPT client not running"
    box = _composer(win)
    if box is None:
        return False, "ChatGPT message input box not found"
    try:
        box.SetFocus()
    except Exception:
        pass
    try:
        box.Click(simulateMove=False)
    except Exception:
        try:
            x, y = box.GetClickablePoint()
            auto.Click(x, y)
        except Exception:
            return False, "Failed to click composer input box"
    time.sleep(0.2)
    auto.SendKeys("{Ctrl}a", waitTime=0.05)
    auto.SendKeys("{Delete}", waitTime=0.05)
    if text:
        try:
            vp = box.GetPattern(auto.PatternId.ValuePattern)
            if vp:
                vp.SetValue(text)
                time.sleep(0.15)
        except Exception:
            pass
        current_val = (read_composer_text() or "").strip()
        if current_val != text.strip():
            safe_keys = text.replace("{", "{{}").replace("}", "{}}")
            auto.SendKeys(safe_keys, waitTime=0.15)
            time.sleep(0.2)
    return True, ""


def read_composer_text():
    win = discovery.find_window()
    if win is None:
        return None
    box = _composer(win)
    if box is None:
        return None
    try:
        vp = box.GetPattern(auto.PatternId.ValuePattern)
        return ((vp.Value if vp else "") or "").rstrip("\r\n")
    except Exception:
        return None


def send_message():
    win = discovery.find_window()
    if win is None:
        return False, "ChatGPT client not running"

    how_used = ""
    for _ in range(3):
        win = discovery.find_window()
        if win is None:
            break
        for label in C.SEND_LABELS:
            ctrl = find_button(win, label)
            if ctrl is not None:
                how = _invoke(ctrl)
                if how:
                    how_used = f"Clicked {label} button ({how})"
                    break
        if how_used:
            break
        time.sleep(0.4)

    if not how_used:
        box = _composer(win)
        if box is not None:
            try:
                box.SetFocus()
                box.Click(simulateMove=False)
            except Exception:
                pass
        time.sleep(0.15)
        auto.SendKeys("{Enter}", waitTime=0.25)
        how_used = "Pressed Enter key"

    # Post-send verification: confirm 'Continue' left the input box or generation started
    for _ in range(6):
        time.sleep(0.5)
        rem = (read_composer_text() or "").strip()
        if rem == "" or rem.lower() != "continue":
            return True, how_used + " (verified sent)"
        snap_chk = reader.read()
        if snap_chk.stop_present:
            return True, how_used + " (generation started)"

    return False, how_used + " but 'Continue' remained unsubmitted in input box (quota still locked)"



def refresh_ladder(cfg, log, target_thread):
    if not target_thread:
        return False, "L0", reader.read()
    snap = reader.read()
    if not planner.is_stale(snap, reader._now(), cfg):
        return True, "L0", snap

    log.write("warn", "refresh_start", level_detail="L1", thread=snap.thread)

    win = discovery.find_window()
    if win is not None:
        click_button(win, "New chat")
        time.sleep(1.5)
        ok, err = switch_to_thread(target_thread)
        if ok:
            snap = reader.read()
            if not planner.is_stale(snap, reader._now(), cfg):
                log.write("info", "refresh_ok", level_detail="L1")
                return True, "L1", snap
        else:
            log.write("warn", "refresh_l1_fail", detail=err)

    log.write("warn", "refresh_start", level_detail="L2")
    discovery.force_foreground(discovery.find_hwnd())
    auto.SendKeys("{Ctrl}r", waitTime=0.2)
    time.sleep(6.0)
    ok, err = switch_to_thread(target_thread, timeout=15)
    snap = reader.read()
    if not planner.is_stale(snap, reader._now(), cfg):
        log.write("info", "refresh_ok", level_detail="L2")
        return True, "L2", snap
    log.write("error", "refresh_fail", detail="L1/L2 refresh did not clear banner")
    return False, "L1/L2", snap


def run_act(cfg, log, expect_reset_at=None, force=False, retry_count=0):
    hwnd = discovery.find_hwnd()
    if not hwnd:
        return {"ok": False, "action": "none", "detail": "ChatGPT client not running"}

    if not discovery.force_foreground(hwnd):
        log.write("warn", "focus_fail")

    snap = reader.read()
    if cfg.locked_thread and snap.thread != cfg.locked_thread and not cfg.follow_open_thread:
        log.write("info", "switch_back", want=cfg.locked_thread, now_at=snap.thread)
        ok, err = switch_to_thread(cfg.locked_thread)
        if not ok:
            return {"ok": False, "action": "switch", "detail": err}
        snap = reader.read()

    now = reader._now()
    passed = expect_reset_at is not None and now >= expect_reset_at

    # ChatGPT often leaves the quota banner in the DOM after reset time until a new message
    # is sent. When the reset timestamp has passed (or manual resume is forced), send 'Continue'
    # directly so the message itself clears the stale banner.
    if retry_count >= 1 and getattr(snap, 'quota_msgs', None):
        ok, level, snap = refresh_ladder(cfg, log, cfg.locked_thread or snap.thread)
    elif not force and not passed:
        if planner.is_stale(snap, now, cfg):
            ok, level, snap = refresh_ladder(cfg, log, cfg.locked_thread or snap.thread)
        if not planner.should_attempt(snap, now, expect_reset_at, cfg.stale_grace_seconds):
            return {"ok": False, "action": "none", "detail": "Quota still exhausted"}

    if (force or passed) and getattr(snap, "quota_msgs", None):
        reason = "Manual Resume Now triggered" if force else "Quota reset time reached; sending Continue to clear stale banner"
        log.write("warn", "act_forced", detail=reason)

    if not force and not passed and not snap.composer_empty:
        return {"ok": False, "action": "none", "detail": "Composer has unsent draft; skipping"}

    action = planner.choose_act(snap)
    if action == "none":
        if force or passed:
            action = "send_continue"
        else:
            return {"ok": False, "action": "none", "detail": "No action needed"}

    win = discovery.find_window()
    if win is None:
        return {"ok": False, "action": action, "detail": "ChatGPT client not running"}

    if action == "resume_goal":
        how = invoke_resume_goal(win)
        if how:
            log.write("info", "goal_resume_clicked", detail=how)
            return {"ok": True, "action": action, "detail": f"Clicked Resume ({how})"}

    text = cfg.continue_text or "Continue"
    ok, err = set_composer_text(text)
    if not ok:
        return {"ok": False, "action": "send_continue", "detail": err}
    ok, how = send_message()
    if not ok:
        return {"ok": False, "action": "send_continue", "detail": how}
    return {"ok": True, "action": "send_continue", "detail": f"Typed '{text}' & {how}"}
