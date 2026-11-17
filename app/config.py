# -*- coding: utf-8 -*-
"""Configuration loader and saver."""

import json
import os
from dataclasses import dataclass, asdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "AutoResume")
    os.makedirs(path, exist_ok=True)
    return path


def log_dir():
    path = os.path.join(REPO_ROOT, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def assets_dir():
    path = os.path.join(REPO_ROOT, "assets")
    os.makedirs(path, exist_ok=True)
    return path


def config_path():
    return os.path.join(app_dir(), "config.json")


@dataclass
class Config:
    poll_seconds: int = 20
    auto_resume: bool = True
    locked_project: str = ""
    locked_thread: str = ""
    retry_window_minutes: int = 10
    cooldown_seconds: int = 90
    stale_grace_seconds: int = 45
    log_retention_days: int = 30
    continue_text: str = "Continue"
    language: str = "en"
    blocked_confirm_polls: int = 3
    follow_open_thread: bool = True
    autostart: bool = False
    notify_enabled: bool = True
    hw_sleep_wake: bool = True
    wake_lead_minutes: int = 10
    idle_sleep_seconds: int = 300

    @classmethod
    def load(cls):
        path = config_path()
        if not os.path.exists(path):
            cfg = cls()
            cfg.save()
            return cfg
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        cfg = cls()
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        cfg.language = "en"
        if not cfg.continue_text or cfg.continue_text == "\u7ee7\u7eed":
            cfg.continue_text = "Continue"
        return cfg

    def save(self):
        path = config_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def lock(self, project, thread):
        self.locked_project = project or ""
        self.locked_thread = thread or ""
        self.save()
