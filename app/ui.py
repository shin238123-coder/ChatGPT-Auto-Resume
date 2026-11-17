# -*- coding: utf-8 -*-
"""Clean Google Workspace / Material 3 UI with Official Google Material Symbols Font & Custom App Icon."""

import ctypes
import os
import queue
import subprocess
import threading
from datetime import datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import actor, autostart, constants as C, hw_wake, i18n, reader
from .config import assets_dir, log_dir

ctk.set_appearance_mode("light")

G_BG = "#F0F4F9"
G_SURFACE = "#FFFFFF"
G_CHIP_BG = "#F8FAFD"
G_BORDER = "#E0E3E7"
G_BLUE = "#0B57D0"
G_BLUE_HOVER = "#0842A0"
G_TONAL = "#D3E3FD"
G_TONAL_HOVER = "#C2E7FF"
G_TONAL_TEXT = "#041E49"
G_TEXT = "#1F1F1F"
G_SUB = "#444746"
G_MUTED = "#747775"

MAX_LOG_LINES = 30

STATE_PILL = {
    C.ST_RUNNING: ("RUNNING", "#E6F4EA", "#137333"),
    C.ST_QUOTA: ("QUOTA EXHAUSTED", "#FEF7E0", "#B06000"),
    C.ST_NEEDS_PERMISSION: ("NEEDS PERMISSION", "#FCE8E6", "#C5221F"),
    C.ST_NEEDS_REPLY: ("NEEDS REPLY", "#FCE8E6", "#C5221F"),
    C.ST_IDLE: ("READY", "#E8F0FE", "#1967D2"),
    C.ST_APP_MISSING: ("CHATGPT CLOSED", "#F1F3F4", "#5F6368"),
    C.ST_LOCKED_NOT_OPEN: ("STANDBY (OTHER TAB)", "#FEF7E0", "#B06000"),
}


def ensure_app_icon_and_font():
    adir = assets_dir()
    ico_path = os.path.join(adir, "app_icon.ico")
    if not os.path.exists(ico_path):
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((16, 16, 240, 240), radius=56, fill=(11, 87, 208, 255))
        d.arc((56, 56, 200, 200), start=35, end=315, fill=(255, 255, 255, 255), width=20)
        d.polygon([(112, 92), (112, 164), (168, 128)], fill=(194, 231, 255, 255))
        img.save(ico_path, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])

    font_path = os.path.join(adir, "MaterialSymbolsRounded.ttf")
    has_font = False
    if os.path.exists(font_path):
        try:
            added = ctypes.windll.gdi32.AddFontResourceExW(font_path, 0x10, 0)
            has_font = (added > 0)
        except Exception:
            has_font = False
    return ico_path, has_font


def _parse_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _fmt_12h(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


class Dashboard:
    def __init__(self, root, cfg, logbook, engine, events, tray=None):
        self.root = root
        self.cfg = cfg
        self.log = logbook
        self.engine = engine
        self.events = events
        self.tray = tray
        self.last_reset_at = None
        self.last_balance = {"ok": False}
        self.thread_map = {}
        self._closing = False
        self._drain_id = None
        self._tick_id = None

        ico_path, self.has_material_font = ensure_app_icon_and_font()
        try:
            root.iconbitmap(ico_path)
            root.after(200, lambda: root.iconbitmap(ico_path))
        except Exception:
            pass

        root.title("ChatGPT Auto Resume")
        root.geometry("660x680")
        root.minsize(620, 640)
        root.configure(fg_color=G_BG)

        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(3, weight=1)

        self._build()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._drain()
        self._tick()
        root.after(400, self.refresh_threads)

    def _build(self):
        top_bar = ctk.CTkFrame(self.root, fg_color=G_SURFACE, corner_radius=14,
                               border_width=1, border_color=G_BORDER)
        top_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        top_bar.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 6))
        title_box.grid_columnconfigure(0, weight=1)

        self.lbl_mode_tag = ctk.CTkLabel(
            title_box, text="ACTIVE TARGET CONVERSATION  ·  AUTO-FOLLOWING OPEN TAB",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=G_BLUE, anchor="w"
        )
        self.lbl_mode_tag.grid(row=0, column=0, sticky="w")

        self.lbl_badge = ctk.CTkLabel(
            title_box, text="MONITORING",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#E8F0FE", text_color="#1967D2",
            corner_radius=12, padx=12, pady=2
        )
        self.lbl_badge.grid(row=0, column=1, sticky="e")

        self.lbl_thread = ctk.CTkLabel(
            top_bar, text="Reading ChatGPT window...",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=17, weight="bold"),
            text_color=G_TEXT, anchor="w"
        )
        self.lbl_thread.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

        sel_row = ctk.CTkFrame(top_bar, fg_color="transparent")
        sel_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        sel_row.grid_columnconfigure(0, weight=1)

        self.cmb = ctk.CTkComboBox(
            sel_row, values=["Scanning sidebar..."],
            command=self._on_pick, height=34, corner_radius=8,
            fg_color=G_CHIP_BG, border_color=G_BORDER, text_color=G_TEXT,
            button_color="#D3E3FD", button_hover_color="#C2E7FF",
            dropdown_fg_color=G_SURFACE, dropdown_text_color=G_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.cmb.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            sel_row, text="Pin Open Tab", command=self._use_current,
            height=34, width=124, corner_radius=17,
            fg_color=G_TONAL, hover_color=G_TONAL_HOVER, text_color=G_TONAL_TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12)
        ).grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(
            sel_row, text="Scan Sidebar", command=self.refresh_threads,
            height=34, width=116, corner_radius=17,
            fg_color=G_SURFACE, hover_color=G_CHIP_BG, text_color=G_SUB,
            border_width=1, border_color=G_BORDER,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12)
        ).grid(row=0, column=2)

        strip = ctk.CTkFrame(self.root, fg_color=G_SURFACE, corner_radius=14,
                             border_width=1, border_color=G_BORDER)
        strip.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        strip.grid_columnconfigure((0, 1), weight=1)

        t1 = ctk.CTkFrame(strip, fg_color=G_CHIP_BG, corner_radius=10)
        t1.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=(12, 6))
        ctk.CTkLabel(t1, text="NEXT QUOTA RESET", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                     text_color=G_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_reset = ctk.CTkLabel(t1, text="No active limit",
                                      font=ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold"),
                                      text_color=G_TEXT)
        self.lbl_reset.pack(anchor="w", padx=12, pady=(2, 8))

        t2 = ctk.CTkFrame(strip, fg_color=G_CHIP_BG, corner_radius=10)
        t2.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=(12, 6))
        t2_hdr = ctk.CTkFrame(t2, fg_color="transparent")
        t2_hdr.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(t2_hdr, text="PC WAKE ALARM (-10M)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                     text_color=G_MUTED).pack(side="left")
        ctk.CTkButton(
            t2_hdr, text="Verify Alarm", command=self._verify_wake_alarm,
            height=20, width=82, corner_radius=10,
            fg_color=G_TONAL, hover_color=G_TONAL_HOVER, text_color=G_TONAL_TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=10)
        ).pack(side="right")
        self.lbl_wake = ctk.CTkLabel(t2, text="Standby (arms on limit)",
                                     font=ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold"),
                                     text_color=G_SUB)
        self.lbl_wake.pack(anchor="w", padx=12, pady=(2, 8))

        t3 = ctk.CTkFrame(strip, fg_color=G_CHIP_BG, corner_radius=10)
        t3.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(0, 10))
        ctk.CTkLabel(t3, text="5-HOUR ALLOWANCE", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                     text_color=G_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_bal_5h = ctk.CTkLabel(t3, text="—",
                                       font=ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold"),
                                       text_color=G_TEXT)
        self.lbl_bal_5h.pack(anchor="w", padx=12, pady=(2, 8))

        t4 = ctk.CTkFrame(strip, fg_color=G_CHIP_BG, corner_radius=10)
        t4.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=(0, 10))
        ctk.CTkLabel(t4, text="WEEKLY ALLOWANCE", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                     text_color=G_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_bal_wk = ctk.CTkLabel(t4, text="—",
                                       font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
                                       text_color=G_TEXT)
        self.lbl_bal_wk.pack(anchor="w", padx=12, pady=(2, 8))

        prefs = ctk.CTkFrame(self.root, fg_color=G_SURFACE, corner_radius=14,
                             border_width=1, border_color=G_BORDER)
        prefs.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.sw_resume = ctk.CTkSwitch(
            prefs, text="Auto-type 'Continue' at reset & wake sleeping PC 10m early (sleeps after 5m idle)",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=G_TEXT, progress_color=G_BLUE, command=self._on_toggle
        )
        self.sw_resume.pack(anchor="w", padx=16, pady=(12, 6))
        if self.cfg.auto_resume:
            self.sw_resume.select()

        sub_sw = ctk.CTkFrame(prefs, fg_color="transparent")
        sub_sw.pack(fill="x", padx=16, pady=(0, 12))

        self.sw_follow = ctk.CTkSwitch(
            sub_sw, text="Auto-follow open ChatGPT tab",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=G_SUB, progress_color=G_BLUE, command=self._on_follow
        )
        self.sw_follow.pack(side="left", padx=(0, 24))
        if self.cfg.follow_open_thread:
            self.sw_follow.select()

        self.sw_auto = ctk.CTkSwitch(
            sub_sw, text="Start with Windows",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=G_SUB, progress_color=G_BLUE, command=self._on_autostart
        )
        self.sw_auto.pack(side="left")
        if autostart.is_enabled():
            self.sw_auto.select()

        self.lbl_bal_time = ctk.CTkLabel(
            sub_sw, text="", font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=G_MUTED
        )
        self.lbl_bal_time.pack(side="right")

        log_card = ctk.CTkFrame(self.root, fg_color=G_SURFACE, corner_radius=14,
                                border_width=1, border_color=G_BORDER)
        log_card.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 10))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        lhdr = ctk.CTkFrame(log_card, fg_color="transparent")
        lhdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        lhdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(lhdr, text="LIVE EVENT LOG",
                     font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                     text_color=G_MUTED).grid(row=0, column=0, sticky="w")
        self.lbl_phase = ctk.CTkLabel(lhdr, text="Monitoring active chat",
                                      font=ctk.CTkFont(family="Segoe UI Semibold", size=11),
                                      text_color=G_BLUE)
        self.lbl_phase.grid(row=0, column=1, sticky="e")

        self.txt = ctk.CTkTextbox(
            log_card, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#131314", text_color="#E3E3E3",
            corner_radius=8, wrap="word", state="disabled"
        )
        self.txt.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))

        bot = ctk.CTkFrame(self.root, fg_color="transparent")
        bot.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))
        bot.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bot, text="Send 'Continue' to Chat Now", command=self._act_now,
            height=38, width=210, corner_radius=19,
            fg_color=G_BLUE, hover_color=G_BLUE_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13)
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        ctk.CTkButton(
            bot, text="Refresh Status", command=self._check_now,
            height=38, width=140, corner_radius=19,
            fg_color=G_TONAL, hover_color=G_TONAL_HOVER, text_color=G_TONAL_TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13)
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkButton(
            bot, text="View Log File", command=self._open_logs_folder,
            height=38, width=136, corner_radius=19,
            fg_color=G_SURFACE, hover_color=G_CHIP_BG, text_color=G_SUB,
            border_width=1, border_color=G_BORDER,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13)
        ).grid(row=0, column=2, sticky="e")

    def _verify_wake_alarm(self):
        if self.last_reset_at:
            now_dt = datetime.now().astimezone()
            sec_left = (self.last_reset_at - now_dt).total_seconds()
            lead = int(getattr(self.cfg, "wake_lead_minutes", 10))
            wake_dt = self.last_reset_at - timedelta(minutes=lead)
            if 0 < sec_left <= 21600 and wake_dt > now_dt:
                hw_wake.schedule_hardware_wake(wake_dt, self.log)
        rep = hw_wake.verify_wake_configuration()
        ac_ok = "ENABLED" if rep["ac_wake"] else "DISABLED"
        dc_ok = "ENABLED" if rep["dc_wake"] else "DISABLED"
        task_ok = "REGISTERED" if rep["task_exists"] else "Standby (no <=6h limit active)"
        timers = rep["active_timers"] or "None"
        msg = (
            f"1. AC Power Wake Timers:  {ac_ok}\n"
            f"2. Battery Power Wake Timers:  {dc_ok}\n"
            f"3. Scheduled Wake Task ({hw_wake.TASK_NAME}):  {task_ok}\n\n"
            f"Active Windows Hardware Wake Timers:\n{timers}"
        )
        self._append("Wake Audit", f"AC={ac_ok}, Battery={dc_ok}, Task={task_ok}")
        messagebox.showinfo("Hardware Wake Alarm Audit", msg)

    def _open_logs_folder(self):
        folder = os.path.abspath(log_dir())
        os.makedirs(folder, exist_ok=True)
        today_log = os.path.join(folder, datetime.now().strftime("%Y-%m-%d") + ".jsonl")
        if os.path.exists(today_log):
            subprocess.Popen(f'explorer.exe /select,"{today_log}"')
            self._append("Opened log file location", today_log)
        else:
            os.startfile(folder)
            self._append("Opened log folder", folder)

    def refresh_threads(self):
        def _bg():
            try:
                groups = actor.list_conversations()
            except Exception:
                groups = []
            values = []
            tmap = {}
            for group in groups:
                proj = group["project"]
                for conv in group["conversations"]:
                    if conv not in tmap:
                        values.append(conv)
                        tmap[conv] = (proj, conv)
            if not self._closing:
                self.root.after(0, lambda: self._apply_threads(values, tmap))
        threading.Thread(target=_bg, daemon=True).start()

    def _apply_threads(self, values, tmap):
        if self._closing:
            return
        self.thread_map = tmap
        if values:
            self.cmb.configure(values=values)
            if self.cfg.locked_thread in tmap:
                self.cmb.set(self.cfg.locked_thread)
            else:
                self.cmb.set(values[0])
        else:
            self.cmb.configure(values=["(Keep ChatGPT sidebar open & click Scan Sidebar)"])
            self.cmb.set("(Keep ChatGPT sidebar open & click Scan Sidebar)")

    def _on_pick(self, choice):
        if choice not in self.thread_map:
            return
        project, conv = self.thread_map[choice]
        self.sw_follow.deselect()
        self.cfg.follow_open_thread = False
        self.engine.set_target(project, conv)
        self._render_thread_labels(conv, project, conv)
        self._append("Pinned conversation", f"Switching ChatGPT to \"{conv}\"...")

        def _bg_switch():
            actor.switch_to_thread(conv)
            self.engine.due_at = 0
        threading.Thread(target=_bg_switch, daemon=True).start()

    def _use_current(self):
        def _bg():
            with actor.auto.UIAutomationInitializerInThread():
                snap = reader.read()
            if snap.ok and snap.thread and not self._closing:
                self.engine.set_target(snap.project, snap.thread)
                self.root.after(0, lambda: (
                    self._render_thread_labels(snap.thread, snap.project, snap.thread),
                    self._append("Pinned to open tab", f"\"{snap.thread}\"")
                ))
            elif not self._closing:
                self.root.after(0, lambda: messagebox.showinfo(
                    "ChatGPT Auto Resume",
                    "Make sure the ChatGPT window is visible on screen, then click Pin Open Tab."
                ))
        threading.Thread(target=_bg, daemon=True).start()

    def _on_toggle(self):
        want = bool(self.sw_resume.get())
        self.cfg.auto_resume = want
        self.engine.set_enabled(want, self.engine.snap)
        self._append("Auto-Resume " + ("Enabled" if want else "Paused"),
                     "Will wake PC 10m early & send 'Continue' at reset" if want else "Monitoring only")

    def _on_follow(self):
        want = bool(self.sw_follow.get())
        self.cfg.follow_open_thread = want
        self.cfg.save()
        if want:
            def _sync_now():
                with actor.auto.UIAutomationInitializerInThread():
                    snap = reader.read()
                if snap.ok and snap.thread:
                    self.engine.set_target(snap.project, snap.thread)
                self.engine.due_at = 0
            threading.Thread(target=_sync_now, daemon=True).start()
            self._append("Auto-Follow Enabled", "Tracking whichever ChatGPT tab is currently open")
        else:
            self._append("Auto-Follow Paused", f"Pinned to \"{self.cfg.locked_thread}\"")
            self.engine.due_at = 0

    def _on_autostart(self):
        want = bool(self.sw_auto.get())
        try:
            if want:
                autostart.enable()
            else:
                autostart.disable()
            self.cfg.autostart = want
            self.cfg.save()
            self._append("Windows Startup", "Enabled" if want else "Disabled")
        except Exception as exc:
            if want:
                self.sw_auto.deselect()
            else:
                self.sw_auto.select()
            messagebox.showerror("ChatGPT Auto Resume", f"Failed to update startup: {exc}")

    def _act_now(self):
        self.engine.request_act_now()
        self._append("Manual Resume Triggered", "Focusing ChatGPT, typing 'Continue', and clicking Send...")

    def _check_now(self):
        self.engine.due_at = 0
        self.refresh_threads()
        self._append("Refreshed Status", "Polled live ChatGPT window and sidebar conversations")

    def _on_close(self):
        if self.tray is not None:
            self.root.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        self._closing = True
        if self._drain_id is not None:
            try:
                self.root.after_cancel(self._drain_id)
            except Exception:
                pass
        if self._tick_id is not None:
            try:
                self.root.after_cancel(self._tick_id)
            except Exception:
                pass
        try:
            self.engine.stop()
        except Exception:
            pass
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _drain(self):
        if self._closing:
            return
        try:
            while True:
                try:
                    evt = self.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_event(evt)
                except Exception as exc:
                    try:
                        self._append("UI error", repr(exc)[:90], level="error")
                    except Exception:
                        pass
        finally:
            if not self._closing:
                self._drain_id = self.root.after(200, self._drain)

    def _handle_event(self, evt):
        kind = evt.get("type")
        if kind == "snapshot":
            self._on_snapshot(evt)
        elif kind == "log":
            rec = evt["record"]
            title, detail = self._humanize_log(rec)
            if title:
                self._append(title, detail, ts=rec.get("ts", ""), level=rec.get("level", "info"))
        elif kind == "cmd":
            self._on_command(evt.get("cmd"))
        elif kind == "disabled":
            self.sw_resume.deselect()

    def _on_command(self, cmd):
        if cmd == "show":
            self.show_window()
        elif cmd == "act":
            self.show_window()
            self._act_now()
        elif cmd == "quit":
            self.quit_app()

    def _on_snapshot(self, evt):
        self.last_snapshot = evt
        if bool(self.sw_resume.get()) != bool(self.engine.enabled):
            if self.engine.enabled:
                self.sw_resume.select()
            else:
                self.sw_resume.deselect()

        sb_threads = evt.get("sidebar_threads") or []
        if sb_threads and len(sb_threads) != len(self.thread_map):
            tmap = {c: ("Workspace", c) for c in sb_threads}
            self._apply_threads(sb_threads, tmap)

        thread = evt.get("thread") or ""
        target = evt.get("target") or ""
        proj = evt.get("target_project") or evt.get("project") or ""
        display_thread = thread if self.cfg.follow_open_thread else (target or thread)
        self._render_thread_labels(display_thread, proj, thread)

        self._last_state = evt.get("state")
        self._last_phase = evt.get("phase")
        self.last_reset_at = self._reset_from(evt)
        self._quota_reset_at = self.last_reset_at
        self._render_state_labels()
        self._render_balance(evt.get("balance") or {"ok": False}, self.last_reset_at)

        if self.tray is not None:
            self.tray.set_tooltip(
                f"ChatGPT Auto Resume - {i18n.state_text('en', evt.get('state'))}" +
                (f" - {display_thread}" if display_thread else "")
            )

    def _reset_from(self, evt):
        value = evt.get("reset_at")
        if isinstance(value, str):
            return _parse_iso(value)
        return value

    def _render_thread_labels(self, thread, project, open_thread):
        self.lbl_thread.configure(text=thread or "No conversation detected")
        if self.cfg.follow_open_thread:
            self.lbl_mode_tag.configure(
                text="ACTIVE TARGET CONVERSATION  ·  AUTO-FOLLOWING OPEN TAB",
                text_color=G_BLUE
            )
        else:
            self.lbl_mode_tag.configure(
                text="ACTIVE TARGET CONVERSATION  ·  PINNED TO SELECTED CHAT",
                text_color="#B06000"
            )
        if thread and thread in self.thread_map:
            self.cmb.set(thread)
        self._open_thread = open_thread or ""

    def _render_state_labels(self):
        state = getattr(self, "_last_state", None)
        phase = getattr(self, "_last_phase", None)
        if state:
            txt, bg, fg = STATE_PILL.get(state, ("UNKNOWN", "#F1F3F4", "#5F6368"))
            self.lbl_badge.configure(text=txt, fg_color=bg, text_color=fg)
        if phase:
            self.lbl_phase.configure(text=i18n.phase_text("en", phase))

        lead_min = int(getattr(self.cfg, "wake_lead_minutes", 10))
        if self.last_reset_at:
            now_dt = datetime.now().astimezone()
            sec_left = (self.last_reset_at - now_dt).total_seconds()
            wake_dt = self.last_reset_at - timedelta(minutes=lead_min)
            if sec_left > 21600:
                self.lbl_wake.configure(
                    text="Paused (reset > 6h away)",
                    text_color=G_MUTED
                )
            elif now_dt < wake_dt:
                self.lbl_wake.configure(
                    text=f"Armed for {_fmt_12h(wake_dt)}",
                    text_color="#137333"
                )
            else:
                self.lbl_wake.configure(
                    text="PC Awake — Ready for Reset",
                    text_color=G_BLUE
                )
        elif state == C.ST_QUOTA:
            self.lbl_reset.configure(text="Reading banner...", text_color="#B06000")
            self.lbl_wake.configure(text="Pending...", text_color=G_MUTED)
        else:
            self.lbl_reset.configure(text="No active limit", text_color=G_TEXT)
            self.lbl_wake.configure(text="Standby (arms on limit)", text_color=G_MUTED)

    def _render_balance(self, bal, quota_reset_at=None):
        self.last_balance = bal or {"ok": False}
        self._quota_reset_at = quota_reset_at
        if not self.last_balance.get("ok"):
            self.lbl_bal_5h.configure(text="—", text_color=G_MUTED)
            self.lbl_bal_wk.configure(text="—", text_color=G_MUTED)
            return
        now = datetime.now().astimezone()

        five = self.last_balance.get("five_hour") or {}
        pct5 = five.get("remaining_percent")
        if getattr(self, "_last_state", None) == C.ST_QUOTA:
            pct5 = 0.0

        if pct5 is not None:
            p_int = int(pct5)
            color5 = "#C5221F" if p_int <= 10 else ("#B06000" if p_int <= 30 else "#137333")
            tag = " (Exhausted)" if p_int == 0 else " remaining"
            self.lbl_bal_5h.configure(text=f"{p_int}%{tag}", text_color=color5)
        else:
            self.lbl_bal_5h.configure(text="Available", text_color="#137333")

        week = self.last_balance.get("weekly") or {}
        pct_wk = week.get("remaining_percent")
        reset_wk = _parse_iso(week.get("resets_at"))
        if pct_wk is not None:
            pw_int = int(pct_wk)
            wk_str = f"{pw_int}% left"
            if reset_wk:
                rem_sec = max(0, int((reset_wk - now).total_seconds()))
                days, rem_s = divmod(rem_sec, 86400)
                hours = rem_s // 3600
                wk_str += f"  ·  Resets in {days}d {hours}h ({reset_wk.strftime('%b %d, %I:%M %p').replace(' 0', ' ')})"
            self.lbl_bal_wk.configure(text=wk_str, text_color=G_TEXT)
        else:
            self.lbl_bal_wk.configure(text="—", text_color=G_MUTED)

        observed = _parse_iso(self.last_balance.get("observed_at"))
        source = self.last_balance.get("source") or "Live UI"
        if observed:
            self.lbl_bal_time.configure(text=f"{source} · {self._ago(observed, now)}")

    def _ago(self, when, now):
        seconds = max(0, (now - when).total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 48 * 3600:
            return f"{int(seconds // 3600)}h ago"
        return f"{int(seconds // 86400)}d ago"

    def _tick(self):
        if self._closing:
            return
        if self.last_reset_at:
            left = int((self.last_reset_at - datetime.now().astimezone()).total_seconds())
            if left > 0:
                h, rem = divmod(left, 3600)
                m, s = divmod(rem, 60)
                if h >= 24:
                    d, h_rem = divmod(h, 24)
                    dt_str = f"{self.last_reset_at.strftime('%b %d')}, {_fmt_12h(self.last_reset_at)}"
                    self.lbl_reset.configure(
                        text=f"{dt_str} (in {d}d {h_rem:02d}h {m:02d}m)",
                        text_color="#B06000"
                    )
                else:
                    self.lbl_reset.configure(
                        text=f"{_fmt_12h(self.last_reset_at)} (in {h:02d}h {m:02d}m {s:02d}s)",
                        text_color="#B06000"
                    )
            elif left > -120:
                self.lbl_reset.configure(text="Resetting now — sending Continue...", text_color=G_BLUE)
            else:
                self.lbl_reset.configure(text="No active limit", text_color=G_TEXT)
        if not self._closing:
            self._tick_id = self.root.after(1000, self._tick)

    def _humanize_log(self, rec):
        ev = rec.get("event", "")
        if ev == "app_start":
            return "App Ready", f"Target: \"{rec.get('locked') or 'Active tab'}\""
        if ev == "hw_wake_scheduled":
            return ("Wake Alarm Armed" if rec.get("ok") else "Wake Alarm Failed"), (rec.get("detail") or f"PC will wake at {rec.get('wake_at')}")
        if ev == "hw_entering_sleep":
            return "Sleeping PC", f"Idle {rec.get('idle_sec', 300)}s -> Modern Standby"
        if ev == "hw_woke_up":
            return "PC Woke Up", "Wi-Fi reconnected; awaiting quota reset"
        if ev in ("thread_followed", "thread_locked"):
            return "Target Locked", f"\"{rec.get('thread')}\""
        if ev == "act":
            return ("Sent Continue" if rec.get("ok") else "Continue Retry"), rec.get("detail", "")
        if ev == "locked_not_open":
            return "Other Tab Open", f"Viewing \"{rec.get('now_at')}\" (will switch back to \"{rec.get('target')}\" at reset)"
        if ev == "poll":
            st = i18n.state_text("en", rec.get("state"))
            rst = rec.get("reset_clock")
            if rst:
                return "Limit Active", f"Resets at {rst} · Chat: \"{rec.get('thread')}\""
            return "Polled", f"{st} · Chat: \"{rec.get('thread') or 'ChatGPT'}\""
        return ev.replace("_", " ").capitalize(), rec.get("detail", "")

    def _append(self, title, detail="", ts=None, level="info"):
        if self._closing:
            return
        stamp = ts or datetime.now().astimezone().isoformat(timespec="seconds")
        stamp = stamp[11:19] if len(stamp) >= 19 else stamp
        tag = {"error": "ERR", "warn": "WARN", "info": "OK"}.get(level, "INFO")
        line = f"{stamp}  [{tag}]  {title}" + (f" — {detail}" if detail else "") + "\n"
        self.txt.configure(state="normal")
        self.txt.insert("end", line)
        total = int(self.txt.index("end-1c").split(".")[0]) - 1
        if total > MAX_LOG_LINES:
            self.txt.delete("1.0", f"{total - MAX_LOG_LINES + 1}.0")
        self.txt.see("end")
        self.txt.configure(state="disabled")
