# -*- coding: utf-8 -*-
"""UI labels, state enums, and threshold constants (100% English)."""

PROCESS_NAME = "ChatGPT.exe"
WINDOW_CLASS = "Chrome_WidgetWin_1"

STOP_LABELS = ("Stop generating", "Stop response", "Stop")

APPROVAL_LABELS = (
    "Allow once", "Allow for this chat", "Always allow", "Deny",
    "Approval options", "Allow"
)

WAITING_TEXT = "Waiting for your"

QUOTA_HINTS = (
    "usage limit", "rate limit", "out of codex and work usage",
    "hit your usage limit", "try again at", "resets on", "resets at"
)

GOAL_STALLED = "Goal stalled"
GOAL_ACTIVE = "Active goal"
GOAL_PAUSED = "Goal paused"
GOAL_DONE = "Goal completed"
GOAL_LIMITED = (
    "Goal limited", "Goal usage limit", "Goal restricted",
    "You're out of Codex and Work usage"
)
GOAL_LABELS = (GOAL_STALLED, GOAL_ACTIVE, GOAL_PAUSED, GOAL_DONE) + GOAL_LIMITED

GM_NONE = "none"
GM_ACTIVE = "active"
GM_PAUSED = "paused"
GM_BLOCKED = "blocked"
GM_COMPLETED = "completed"
GM_LIMITED = "limited"
GM_BLOCKED_BY_QUOTA = "blocked_by_quota"
GM_LIMITED_BY_QUOTA = "limited_by_quota"

GM_TERMINAL = (GM_BLOCKED, GM_COMPLETED)
GM_NOTIFY_ONLY = (GM_LIMITED,)

GOAL_RESUME = "Resume goal"
GOAL_PAUSE = "Pause goal"
GOAL_CLEAR = "Clear goal"
GOAL_EDIT = "Edit goal"
GOAL_RESUME_CONFIRM = "Continue goal"

SEND_LABELS = ("Send", "Send message", "Send prompt", "Submit", "Up arrow")
COMPOSER_CLASS_MARK = "ProseMirror"

ST_APP_MISSING = "app_missing"
ST_RUNNING = "running"
ST_NEEDS_PERMISSION = "needs_permission"
ST_NEEDS_REPLY = "needs_reply"
ST_QUOTA = "quota_exhausted"
ST_IDLE = "idle"
ST_LOCKED_MISSING = "locked_thread_missing"
ST_LOCKED_NOT_OPEN = "locked_thread_not_open"

PHASE_OFF = "off"
PHASE_MONITOR = "monitor"
PHASE_WAIT_RESET = "wait_reset"
PHASE_WAIT_UNKNOWN = "wait_unknown"
PHASE_REFRESH = "refresh"
PHASE_ACT = "act"
PHASE_COOLDOWN = "cooldown"
PHASE_NEEDS_HUMAN = "needs_human"
PHASE_APP_MISSING = "app_missing"
PHASE_LOCKED_NOT_OPEN = "locked_not_open"
