# -*- coding: utf-8 -*-
"""English UI string table."""

LANG_ORDER = ["en"]
LANG_NATIVE = {"en": "English"}
DEFAULT_LANG = "en"

STRINGS = {
    "en": {
        "app_title": "ChatGPT Auto Resume",
        "st_running": "Running",
        "st_quota": "Quota Exhausted",
        "st_needs_permission": "Needs Permission",
        "st_needs_reply": "Waiting for Reply",
        "st_idle": "Idle / Ready",
        "st_app_missing": "ChatGPT Closed",
        "st_locked_not_open": "Other Tab Open",
        "ph_off": "Paused",
        "ph_monitor": "Monitoring active chat",
        "ph_wait_reset": "Waiting for quota reset (Hardware Wake Armed)",
        "ph_wait_unknown": "Waiting for quota (no reset time)",
        "ph_refresh": "Refreshing ChatGPT quota...",
        "ph_act": "Typing 'Continue' & clicking Send...",
        "ph_cooldown": "Resumed — verifying response",
        "ph_needs_human": "Needs your attention in ChatGPT",
        "ph_app_missing": "Waiting for ChatGPT app to open",
        "ph_locked_not_open": "Will switch back to pinned chat at reset",
        "notify_permission": "ChatGPT is waiting for permission approval",
        "notify_reply": "ChatGPT is waiting for your reply",
        "notify_goal_blocked": "Task blocked. Check the conversation.",
        "notify_goal_limited": "Task limited. Check the conversation.",
        "notify_goal_completed": "Task completed.",
        "notify_halt_title": "Auto Resume paused",
        "notify_halt_body": "Still failing after {n} attempts: {detail}",
        "cont": "Continue",
    }
}

STATE_KEY = {
    "running": "st_running",
    "quota_exhausted": "st_quota",
    "needs_permission": "st_needs_permission",
    "needs_reply": "st_needs_reply",
    "idle": "st_idle",
    "app_missing": "st_app_missing",
    "locked_thread_missing": "st_locked_not_open",
    "locked_thread_not_open": "st_locked_not_open",
}

PHASE_KEY = {
    "off": "ph_off",
    "monitor": "ph_monitor",
    "wait_reset": "ph_wait_reset",
    "wait_unknown": "ph_wait_unknown",
    "refresh": "ph_refresh",
    "act": "ph_act",
    "cooldown": "ph_cooldown",
    "needs_human": "ph_needs_human",
    "app_missing": "ph_app_missing",
    "locked_not_open": "ph_locked_not_open",
}


def normalize(code=None):
    return "en"


def t(lang, key, **kwargs):
    text = STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def state_text(lang, code):
    key = STATE_KEY.get(code)
    return t("en", key) if key else (code or "")


def phase_text(lang, code):
    key = PHASE_KEY.get(code)
    return t("en", key) if key else (code or "")


def goal_text(lang, mode):
    return mode or ""


def continue_text(lang=None):
    return "Continue"
