# -*- coding: utf-8 -*-
"""ChatGPT Auto Resume main entry point with custom Windows Taskbar AppUserModelID."""

import ctypes
import os
import queue
import sys
from tkinter import messagebox

import customtkinter as ctk

from app.config import Config, app_dir, assets_dir
from app.engine import Engine
from app.logbook import LogBook
from app.notify import Notifier
from app.tray import Tray
from app.ui import Dashboard, ensure_app_icon_and_font

MUTEX_NAME = "Global\\AutoResumeAssistant"
ERROR_ALREADY_EXISTS = 183


def single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return handle, ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def main():
    # Bind explicit AppUserModelID BEFORE creating any window so Windows Taskbar shows our custom icon
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shino.ChatGPT.AutoResume.2")
    except Exception:
        pass

    handle, existed = single_instance()
    if existed:
        root = ctk.CTk()
        root.withdraw()
        messagebox.showinfo("ChatGPT Auto Resume", "ChatGPT Auto Resume is already running (check your system tray).")
        root.destroy()
        return 0

    ico_path, _ = ensure_app_icon_and_font()
    cfg = Config.load()
    events = queue.Queue()
    log = LogBook(retention_days=cfg.log_retention_days)
    log.on_write = lambda rec: events.put({"type": "log", "record": rec})

    root = ctk.CTk()
    try:
        root.iconbitmap(ico_path)
    except Exception:
        pass

    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    except Exception:
        hwnd = 0
    notifier = Notifier(hwnd, log)
    engine = Engine(cfg, log, events.put, notifier)

    tray = Tray(
        on_show=lambda: events.put({"type": "cmd", "cmd": "show"}),
        on_act=lambda: events.put({"type": "cmd", "cmd": "act"}),
        on_quit=lambda: events.put({"type": "cmd", "cmd": "quit"}),
        logbook=log,
    )
    tray_ok = tray.start()

    ui = Dashboard(root, cfg, log, engine, events, tray if tray_ok else None)
    engine.start()

    log.write("info", "app_start", dir=app_dir(), auto_resume=cfg.auto_resume,
              tray=tray_ok, locked=cfg.locked_thread or None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
