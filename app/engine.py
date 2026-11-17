# -*- coding: utf-8 -*-
"""Background polling and hardware sleep/wake orchestration engine."""

import threading
import time
from datetime import timedelta

import uiautomation as auto

from . import actor, constants as C, hw_wake, i18n, planner, ratelimit, reader


class Engine(threading.Thread):
    def __init__(self, cfg, logbook, emit, notifier=None):
        super().__init__(daemon=True, name="auto-resume-engine")
        self.cfg = cfg
        self.log = logbook
        self.emit = emit
        self.notifier = notifier
        self._stop = threading.Event()
        self.enabled = bool(cfg.auto_resume)
        self.phase = C.PHASE_MONITOR if self.enabled else C.PHASE_OFF
        self.prev_state = ""
        self.due_at = time.time()
        self.attempts = 0
        self.halted = False
        self._last_notify = None
        self._manual = False
        self.snap = None
        self.balance = {"ok": False}
        self.last_reset = None
        self.last_reset_clock = ""
        self.last_scheduled_wake = None
        self.goal_mode = C.GM_NONE
        self.goal_end = None
        self._terminal_handled = None
        self._limited_notified = None
        self._blocked_polls = 0
        self._unknown_quota_polls = 0
        self._reset_attempted = False
        self._completed_reset_clock = ""
        self._completed_reset_mono = 0.0
        self._last_cycle_wall = time.time()

    def stop(self):
        hw_wake.release_wake_lock()
        self._stop.set()

    def set_enabled(self, value, snap=None):
        if value:
            self.enabled = True
            self.halted = False
            self.attempts = 0
            self.phase = C.PHASE_MONITOR
            self.prev_state = ""
            self.due_at = time.time()
            self.cfg.auto_resume = True
            if snap is not None and snap.thread:
                self.cfg.lock(snap.project, snap.thread)
            else:
                self.cfg.save()
        else:
            self.enabled = False
            self.phase = C.PHASE_OFF
            hw_wake.release_wake_lock()
            self.cfg.auto_resume = False
            self.cfg.save()

    def request_act_now(self):
        self.halted = False
        self.attempts = 0
        self._manual = True
        self.due_at = 0

    def set_target(self, project, thread):
        self.cfg.lock(project, thread)
        self.prev_state = ""
        self.phase = C.PHASE_MONITOR
        self.due_at = 0

    def run(self):
        auto.InitializeUIAutomationInCurrentThread()
        try:
            while not self._stop.is_set():
                if time.time() >= self.due_at:
                    try:
                        self._cycle()
                    except Exception as exc:
                        self.log.write("error", "cycle_error", detail=repr(exc))
                        self.due_at = time.time() + 30
                time.sleep(0.25)
        finally:
            hw_wake.release_wake_lock()
            auto.UninitializeUIAutomationInCurrentThread()

    def _publish(self, snap, state):
        self.snap = snap
        payload = {
            "type": "snapshot",
            "ok": snap.ok,
            "project": snap.project,
            "thread": snap.thread,
            "state": state,
            "phase": self.phase,
            "language": "en",
            "reset_clock": snap.reset_clock,
            "reset_at": snap.reset_at,
            "read_ms": snap.read_ms,
            "goal_status": snap.goal_status,
            "composer_empty": snap.composer_empty,
            "send_present": snap.send_present,
            "target": self.cfg.locked_thread,
            "target_project": self.cfg.locked_project,
            "follow": bool(self.cfg.follow_open_thread),
            "balance": self.balance,
            "goal_mode": self.goal_mode,
            "goal_end": self.goal_end,
            "sidebar_threads": getattr(snap, "sidebar_threads", []),
        }
        self.emit(payload)

    def _normalize_reset_timestamp(self, snap, now):
        if (
            snap.reset_clock
            and snap.reset_clock == self._completed_reset_clock
            and (time.monotonic() - self._completed_reset_mono) < 600
        ):
            snap.reset_at = None
            snap.reset_clock = ""
            if hasattr(snap, "quota_msgs"):
                snap.quota_msgs = []
            return

        if snap.reset_at is None:
            return

        yesterday_candidate = snap.reset_at - timedelta(days=1)
        past_sec = (now - yesterday_candidate).total_seconds()
        if 0 <= past_sec <= 14400:
            snap.reset_at = yesterday_candidate
            return

        if (
            self.last_reset is not None
            and not self._reset_attempted
            and (now - self.last_reset).total_seconds() >= -900
            and (snap.reset_at - self.last_reset).total_seconds() > 43200
        ):
            snap.reset_at = self.last_reset

    def _cycle(self):
        now_wall = time.time()
        if now_wall - getattr(self, "_last_cycle_wall", now_wall) > 45.0:
            hw_wake._last_wake_mono = time.monotonic()
        self._last_cycle_wall = now_wall

        now = reader._now()
        snap = reader.read()
        self._normalize_reset_timestamp(snap, now)

        state = planner.classify(snap)
        try:
            self.balance = ratelimit.read_limits(snap=snap, state=state)
        except Exception as exc:
            self.balance = {"ok": False, "error": repr(exc)}

        self.goal_mode = planner.goal_mode(snap, state)

        if snap.reset_at is not None:
            if self.last_reset is None or abs((snap.reset_at - self.last_reset).total_seconds()) > 60:
                self._reset_attempted = False
            self.last_reset = snap.reset_at
            self.last_reset_clock = snap.reset_clock
        elif state == C.ST_QUOTA and self.last_reset is not None:
            snap.reset_at = self.last_reset
            snap.reset_clock = self.last_reset_clock
        elif state in (C.ST_IDLE, C.ST_RUNNING) and not snap.quota_msgs:
            if self.last_reset is not None:
                self.last_reset = None
                self.last_reset_clock = ""
                self.last_scheduled_wake = None
                hw_wake.cancel_hardware_wake()
                hw_wake.release_wake_lock()

        if not self.enabled:
            self.phase = C.PHASE_OFF
            hw_wake.release_wake_lock()
            self._publish(snap, state)
            if state != self.prev_state:
                self.log.write("info", "poll", state=state, phase=C.PHASE_OFF,
                               read_ms=snap.read_ms, thread=snap.thread or None)
                self.prev_state = state
            self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            return

        if not self.cfg.locked_thread and snap.thread:
            self.cfg.lock(snap.project, snap.thread)
            self.log.write("info", "thread_locked", thread=snap.thread, project=snap.project)

        if self.cfg.follow_open_thread and snap.thread and snap.thread != self.cfg.locked_thread:
            self.cfg.lock(snap.project, snap.thread)
            self.prev_state = ""
            self.log.write("info", "thread_followed", thread=snap.thread, project=snap.project)

        if self._manual:
            self._manual = False
            self._publish(snap, state)
            self.log.write("info", "manual_act", state=state)
            self._execute(manual=True)
            self.prev_state = state
            return

        target_rst = snap.reset_at or self.last_reset
        reset_is_due = (
            target_rst is not None
            and not self._reset_attempted
            and (now - target_rst).total_seconds() >= 15.0
        )

        if reset_is_due:
            hw_wake._last_wake_mono = time.monotonic()
            self._reset_attempted = True
            self.log.write("info", "quota_reset_due", reset_at=str(target_rst),
                           thread=self.cfg.locked_thread or snap.thread)
            self._execute(manual=False)
            self.prev_state = state
            return

        if target_rst is not None and getattr(self.cfg, "hw_sleep_wake", True):
            sec_until_reset = (target_rst - now).total_seconds()
            if sec_until_reset > 21600:
                # Multi-day / Weekly reset (> 6h away): do NOT arm daily wake timer or force 5m idle sleep
                if self.last_scheduled_wake is not None:
                    hw_wake.cancel_hardware_wake()
                    hw_wake.release_wake_lock()
                    self.last_scheduled_wake = None
            else:
                lead = int(getattr(self.cfg, "wake_lead_minutes", 10))
                wake_dt = target_rst - timedelta(minutes=lead)
                sleep_cutoff_dt = wake_dt - timedelta(minutes=2)

                if now < sleep_cutoff_dt:
                    if self.last_scheduled_wake != wake_dt:
                        hw_wake.schedule_hardware_wake(wake_dt, self.log)
                        self.last_scheduled_wake = wake_dt
                    idle_thresh = int(getattr(self.cfg, "idle_sleep_seconds", 300))
                    if hw_wake.get_idle_seconds() >= idle_thresh:
                        self._publish(snap, state)
                        hw_wake.enter_sleep(self.log)
                        self.due_at = time.time() + 5
                        return
                else:
                    hw_wake.poke_awake(reset_input=False)

        if (
            snap.ok
            and self.cfg.locked_thread
            and snap.thread
            and snap.thread != self.cfg.locked_thread
            and not self.cfg.follow_open_thread
        ):
            self.phase = C.PHASE_LOCKED_NOT_OPEN
            self._publish(snap, C.ST_LOCKED_NOT_OPEN)
            if self.prev_state != C.ST_LOCKED_NOT_OPEN:
                self.log.write("warn", "locked_not_open",
                               target=self.cfg.locked_thread, now_at=snap.thread)
                self.prev_state = C.ST_LOCKED_NOT_OPEN
            if target_rst is not None and now < target_rst:
                rem = max(2.0, (target_rst - now).total_seconds())
                self.due_at = time.time() + min(float(self.cfg.poll_seconds), rem)
            else:
                self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            return

        if self.goal_mode == C.GM_BLOCKED:
            self._blocked_polls += 1
        else:
            self._blocked_polls = 0

        if self._should_terminate(snap):
            if self._terminal_handled != self.goal_mode:
                self._finish_monitor(snap, state)
            else:
                self.phase = C.PHASE_NEEDS_HUMAN
                self._publish(snap, state)
                self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            self.prev_state = state
            return
        self._terminal_handled = None

        if self.goal_mode in C.GM_NOTIFY_ONLY:
            self.phase = C.PHASE_NEEDS_HUMAN
            self._publish(snap, state)
            if self._limited_notified != snap.goal_status:
                self._limited_notified = snap.goal_status
                self._notify(i18n.t("en", "app_title"), i18n.t("en", "notify_goal_limited"), "warn")
                self.log.write("warn", "goal_limited", goal=snap.goal_status)
            self.due_at = time.time() + max(2, int(self.cfg.poll_seconds))
            self.prev_state = state
            return
        self._limited_notified = None

        plan = planner.plan_after_poll(snap, self.phase, self.prev_state, now, self.cfg)
        if plan["phase"] == C.PHASE_WAIT_UNKNOWN:
            self._unknown_quota_polls = getattr(self, "_unknown_quota_polls", 0) + 1
            if self._unknown_quota_polls >= 3 and not self.halted:
                self._unknown_quota_polls = 0
                self.log.write("warn", "wait_unknown_recovery",
                               detail="Banner has no reset timestamp for 3 polls; refreshing & attempting Continue")
                actor.refresh_ladder(self.cfg, self.log, self.cfg.locked_thread or snap.thread)
                self._execute(manual=False)
                self.prev_state = state
                return
        else:
            self._unknown_quota_polls = 0

        self.phase = plan["phase"]
        self._publish(snap, state)

        self.log.write("info", "poll", state=state, phase=plan["phase"],
                       read_ms=snap.read_ms,
                       thread=snap.thread or None,
                       reset_clock=snap.reset_clock or None,
                       reset_at=(snap.reset_at.isoformat(timespec="minutes") if snap.reset_at else None),
                       goal_status=snap.goal_status or None)

        if plan["notify"]:
            if plan["notify"] != self._last_notify:
                title = i18n.t("en", "app_title")
                body = i18n.t("en", "notify_" + plan["notify"])
                self._notify(title, body, "warn")
                self._last_notify = plan["notify"]
        else:
            self._last_notify = None

        if plan["act"] and not self.halted:
            self._execute()
        else:
            self.due_at = time.time() + max(2, plan["due_in"])
        self.prev_state = state

    def _should_terminate(self, snap):
        if self.goal_mode == C.GM_COMPLETED:
            return True
        if self.goal_mode != C.GM_BLOCKED:
            return False
        if self.last_reset is not None:
            return False
        limit = max(1, int(getattr(self.cfg, "blocked_confirm_polls", 3)))
        return self._blocked_polls >= limit

    def _finish_monitor(self, snap, state):
        now = reader._now()
        self._terminal_handled = self.goal_mode
        self.goal_end = {
            "mode": self.goal_mode,
            "at": now.isoformat(timespec="seconds"),
            "goal": snap.goal_status,
        }
        self.log.write("info", "goal_terminal", mode=self.goal_mode,
                       at=now.isoformat(timespec="seconds"),
                       goal=snap.goal_status, thread=snap.thread or None)

        self.phase = C.PHASE_NEEDS_HUMAN
        self._publish(snap, state)

        key = "notify_goal_completed" if self.goal_mode == C.GM_COMPLETED else "notify_goal_blocked"
        self._notify(i18n.t("en", "app_title"), i18n.t("en", key, time=now.strftime("%H:%M")), "info")

        self.set_enabled(False)
        self.phase = C.PHASE_NEEDS_HUMAN
        self.due_at = time.time() + 3600
        self.emit({"type": "disabled", "reason": self.goal_mode})

    def _execute(self, manual=False):
        self.phase = C.PHASE_ACT
        self.emit({"type": "phase", "phase": self.phase, "phase_text": "Sending continuation"})
        res = actor.run_act(self.cfg, self.log, expect_reset_at=self.last_reset, force=manual, retry_count=self.attempts)
        level = "info" if res["ok"] else "warn"
        self.log.write(level, "act", action=res["action"], ok=res["ok"],
                       detail=res["detail"], manual=manual or None)

        if res["ok"]:
            self.attempts = 0
            self._completed_reset_clock = self.last_reset_clock or ""
            self._completed_reset_mono = time.monotonic()
            self.last_reset = None
            self.last_reset_clock = ""
            self.last_scheduled_wake = None
            self._reset_attempted = False
            hw_wake.cancel_hardware_wake()
            hw_wake.release_wake_lock()
            self.phase = C.PHASE_COOLDOWN
            self.due_at = time.time() + int(self.cfg.cooldown_seconds)
            return

        if manual:
            self.phase = C.PHASE_MONITOR
            self.due_at = time.time() + int(self.cfg.poll_seconds)
            return

        self.attempts += 1
        limit = max(1, int(self.cfg.retry_window_minutes))
        if self.attempts >= limit:
            self.halted = True
            self.phase = C.PHASE_NEEDS_HUMAN
            hw_wake.release_wake_lock()
            self.due_at = time.time() + 3600
            self._notify(i18n.t("en", "notify_halt_title"),
                         i18n.t("en", "notify_halt_body", n=limit, detail=res["detail"]),
                         "error")
        else:
            self._reset_attempted = False
            self.phase = C.PHASE_REFRESH
            self.due_at = time.time() + 30

    def _notify(self, title, text, level="info"):
        if self.notifier is None:
            return
        if not self.notifier.notify(title, text, level):
            self.emit({"type": "banner", "text": title + ": " + text})
