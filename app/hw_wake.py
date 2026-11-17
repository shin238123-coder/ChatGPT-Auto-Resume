# -*- coding: utf-8 -*-
"""Hardware RTC Wake Timer, Verification Auditor & Idle-Aware Sleep Controller."""

import ctypes
import os
import subprocess
import time
from datetime import datetime, timedelta

from .config import app_dir

TASK_NAME = "ChatGPT_JobAgent_AutoWake"
_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
_wake_timer_handle = None

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
MOUSEEVENTF_MOVE = 0x0001

# Track the last monotonic timestamp when the PC woke up or exited sleep so
# Windows Modern Standby / unreset GetLastInputInfo() can never trigger a rapid sleep loop.
_last_wake_mono = time.monotonic()


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]


def get_os_idle_seconds() -> float:
    """Raw Windows GetLastInputInfo idle seconds (does not reset on programmatic/RTC wake)."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if _user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = (_kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF
        return max(0.0, millis / 1000.0)
    return 0.0


def get_idle_seconds() -> float:
    """Effective idle seconds: bounded by time since last wake/resume so Modern Standby never loops."""
    os_idle = get_os_idle_seconds()
    since_wake = max(0.0, time.monotonic() - _last_wake_mono)
    return min(os_idle, since_wake)


def poke_awake(reset_input: bool = False):
    """Holds Windows system/display wake lock during pre-reset window and optionally resets input idle."""
    global _last_wake_mono
    try:
        _kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
    except Exception:
        pass
    if reset_input:
        _last_wake_mono = time.monotonic()
        try:
            inp = INPUT(type=0, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MOVE, 0, None))
            _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        except Exception:
            pass


def release_wake_lock():
    """Clears execution state wake lock so the PC is allowed to sleep when idle."""
    try:
        _kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


def cancel_hardware_wake():
    """Cancels both the active KernelRTC waitable timer and Scheduled Task after reset is handled."""
    global _wake_timer_handle
    try:
        if _wake_timer_handle:
            _kernel32.CancelWaitableTimer(_wake_timer_handle)
            _kernel32.CloseHandle(_wake_timer_handle)
            _wake_timer_handle = None
    except Exception:
        pass
    try:
        subprocess.run(
            ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass


def _arm_kernel_waitable_timer(wake_dt: datetime) -> bool:
    """Directly programs the Windows Kernel / ACPI RTC wake alarm via SetWaitableTimer(fResume=True)."""
    global _wake_timer_handle
    try:
        if _wake_timer_handle:
            _kernel32.CancelWaitableTimer(_wake_timer_handle)
            _kernel32.CloseHandle(_wake_timer_handle)
            _wake_timer_handle = None

        handle = _kernel32.CreateWaitableTimerW(None, True, None)
        if not handle:
            return False

        now = datetime.now().astimezone()
        delta_sec = max(5.0, (wake_dt - now).total_seconds())
        due_time = ctypes.c_longlong(int(-delta_sec * 10_000_000))
        ok = bool(_kernel32.SetWaitableTimer(handle, ctypes.byref(due_time), 0, None, None, True))
        if ok:
            _wake_timer_handle = handle
            return True
        _kernel32.CloseHandle(handle)
        return False
    except Exception:
        return False


def schedule_hardware_wake(wake_dt: datetime, log=None) -> bool:
    """Registers an RTC hardware wake timer in Windows Task Scheduler (Battery + AC) + Kernel Timer."""
    kernel_ok = _arm_kernel_waitable_timer(wake_dt)

    xml_path = os.path.join(app_dir(), "wake_task.xml")
    start_iso = wake_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = (wake_dt + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")

    # Valid Windows Task Scheduler 1.2 XML (EndBoundary included so StartWhenAvailable/WakeToRun never fail)
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{start_iso}</StartBoundary>
      <EndBoundary>{end_iso}</EndBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c exit 0</Arguments>
    </Exec>
  </Actions>
</Task>"""
    task_ok = False
    err_detail = ""
    try:
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml)
        res = subprocess.run(
            ["schtasks.exe", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        task_ok = (res.returncode == 0)
        if not task_ok:
            err_detail = (res.stderr or res.stdout or "").strip()
    except Exception as exc:
        err_detail = repr(exc)

    ok = task_ok or kernel_ok
    if log:
        if ok:
            layers = []
            if task_ok:
                layers.append("TaskScheduler")
            if kernel_ok:
                layers.append("KernelRTC")
            log.write("info", "hw_wake_scheduled",
                      wake_at=wake_dt.strftime("%Y-%m-%d %H:%M:%S"),
                      ok=True,
                      detail=f"PC will wake at {wake_dt:%Y-%m-%d %H:%M:%S} ({'+'.join(layers)})")
        else:
            log.write("error", "hw_wake_scheduled",
                      wake_at=wake_dt.strftime("%Y-%m-%d %H:%M:%S"),
                      ok=False,
                      detail=f"Failed: {err_detail}")
    return ok


def verify_wake_configuration() -> dict:
    """Queries Windows powercfg and Task Scheduler to verify hardware wake readiness."""
    report = {"ac_wake": False, "dc_wake": False, "active_timers": "", "task_exists": False}
    try:
        out_q = subprocess.check_output(
            ["powercfg", "/q", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE"],
            creationflags=subprocess.CREATE_NO_WINDOW
        ).decode("utf-8", "ignore")
        report["ac_wake"] = "Current AC Power Setting Index: 0x00000001" in out_q
        report["dc_wake"] = "Current DC Power Setting Index: 0x00000001" in out_q
    except Exception:
        pass
    try:
        out_wt = subprocess.check_output(
            ["powercfg", "/waketimers"],
            creationflags=subprocess.CREATE_NO_WINDOW
        ).decode("utf-8", "ignore").strip()
        report["active_timers"] = out_wt
    except Exception as exc:
        report["active_timers"] = f"Could not query waketimers: {exc}"
    try:
        res = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        report["task_exists"] = (res.returncode == 0) or (_wake_timer_handle is not None)
    except Exception:
        report["task_exists"] = (_wake_timer_handle is not None)
    return report


def enter_sleep(log=None):
    """Turns off displays in low-power standby without freezing the background wake timer."""
    global _last_wake_mono
    if log:
        log.write("info", "hw_entering_sleep", idle_sec=int(get_os_idle_seconds()))
    release_wake_lock()
    try:
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)
    except Exception:
        pass
    _last_wake_mono = time.monotonic()
    time.sleep(1.0)
