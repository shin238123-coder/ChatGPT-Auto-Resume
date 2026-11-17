# -*- coding: utf-8 -*-
"""Pure decision logic for Auto Resume."""

from datetime import timedelta
from . import constants as C


def is_waiting_label(name, offscreen=False):
    text = (name or "").strip()
    if not text or offscreen:
        return False
    return text.lower().startswith(C.WAITING_TEXT.lower())


def is_quota_text(name, offscreen=False):
    text = (name or "").strip()
    if not text or offscreen or len(text) <= 8 or len(text) > 200:
        return False
    low = text.lower()
    for prose_marker in (
        "background workers", "i saved", "pending steps", "usage status check",
        "task remains", "items are confirmed", "reported a reset"
    ):
        if prose_marker in low:
            return False
    system_banners = (
        "you've hit your usage limit",
        "you\u2019ve hit your usage limit",
        "you're out of codex and work usage",
        "you\u2019re out of codex and work usage",
        "your rate limit resets",
        "you've reached your usage limit",
        "rate limit reached",
    )
    return any(b in low for b in system_banners)


def classify(snap):
    if not snap.ok:
        return C.ST_APP_MISSING
    if snap.stop_present:
        return C.ST_RUNNING
    if snap.approval:
        return C.ST_NEEDS_PERMISSION
    if snap.waiting_text:
        return C.ST_NEEDS_REPLY
    if snap.quota_msgs:
        return C.ST_QUOTA
    return C.ST_IDLE


def choose_act(snap):
    status = snap.goal_status
    if status == C.GOAL_ACTIVE:
        return "none"
    if status == C.GOAL_DONE:
        return "none"
    if status == C.GOAL_PAUSED:
        return "resume_goal" if C.GOAL_RESUME in snap.goal_actions else "none"
    if status == C.GOAL_STALLED:
        return "resume_goal" if C.GOAL_RESUME in snap.goal_actions else "none"
    if status in C.GOAL_LIMITED:
        return "resume_goal" if C.GOAL_RESUME in snap.goal_actions else "send_continue"
    if status in C.GOAL_LABELS:
        return "none"
    return "send_continue"


def goal_mode(snap, state):
    status = snap.goal_status
    if not status:
        return C.GM_NONE
    if status == C.GOAL_ACTIVE:
        return C.GM_ACTIVE
    if status == C.GOAL_PAUSED:
        return C.GM_PAUSED
    if status == C.GOAL_DONE:
        return C.GM_COMPLETED
    if status in C.GOAL_LIMITED:
        return C.GM_LIMITED_BY_QUOTA if state == C.ST_QUOTA else C.GM_LIMITED
    if status == C.GOAL_STALLED:
        return C.GM_BLOCKED_BY_QUOTA if state == C.ST_QUOTA else C.GM_BLOCKED
    return C.GM_NONE


def should_attempt(snap, now, expect_reset_at=None, grace_seconds=0):
    if not snap.quota_msgs:
        return True
    target = expect_reset_at or snap.reset_at
    if target is None:
        return False
    return now >= target


def is_stale(snap, now, cfg):
    if not snap.quota_msgs or not snap.reset_at:
        return False
    return now >= snap.reset_at


def plan_after_poll(snap, phase, prev_state, now, cfg):
    state = classify(snap)
    poll = cfg.poll_seconds

    if state == C.ST_APP_MISSING:
        return _r(C.PHASE_APP_MISSING, 10, False, None, "Client not running")
    if state == C.ST_RUNNING:
        return _r(C.PHASE_MONITOR, poll, False, None, "Task running")
    if state == C.ST_NEEDS_PERMISSION:
        return _r(C.PHASE_NEEDS_HUMAN, poll, False, "needs_permission", "Waiting for permission")
    if state == C.ST_NEEDS_REPLY:
        return _r(C.PHASE_NEEDS_HUMAN, poll, False, "needs_reply", "Waiting for reply")

    if state == C.ST_QUOTA:
        if snap.reset_at:
            remaining = (snap.reset_at - now).total_seconds()
            if remaining <= 0:
                return _r(C.PHASE_ACT, 0, True, None, "Reset time reached, sending Continue")
            return _r(C.PHASE_WAIT_RESET, min(poll, max(2.0, remaining)), False, None,
                      "Quota exhausted, waiting for " + snap.reset_clock)
        return _r(C.PHASE_WAIT_UNKNOWN, poll, False, None, "Quota exhausted (no reset time)")

    if phase in (C.PHASE_WAIT_RESET, C.PHASE_WAIT_UNKNOWN) :
        return _r(C.PHASE_ACT, 0, True, None, "Quota restored or run finished, continuing")

    return _r(C.PHASE_MONITOR, poll, False, None, "Idle")


def _r(phase, due_in, act, notify, reason):
    return {"phase": phase, "due_in": due_in, "act": act, "notify": notify, "reason": reason}


def _seconds(n):
    return timedelta(seconds=int(n))

