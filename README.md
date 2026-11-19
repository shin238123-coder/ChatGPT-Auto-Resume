# ChatGPT Auto Resume (24/7 Unattended Quota & Wake Manager)

An automated Windows desktop companion for the official ChatGPT Desktop app that monitors long-running agent and Codex sessions, tracks **5-Hour** and **Weekly** usage quotas in real time, manages hybrid AC/Battery power states, and automatically resumes your pinned conversation (`Continue`) the moment your rate limit resets.

---

## Bugs Debugged & Engineering Upgrades
Built on top of the original `GPT_KeepGoing` UI Automation foundation, this project solves several real-world Windows 11, Electron, and hardware power-management failures encountered during 24/7 unattended runs:

- **Automatic Power & Hibernate (`S4`) Provisioning:** On startup, `app/hw_wake.py` automatically checks `powercfg /a`. If Hibernate is disabled on a Windows 11 S0 Modern Standby laptop, it automatically enables Hibernate, activates `RTCWAKE` hardware timers on AC/DC, configures AC/DC sleep timeouts, and disables the Lock Screen on wake (`CONSOLELOCK 0`) via a one-time elevation—no manual `powercfg` commands required.
- **Windows 11 S0 Modern Standby Freeze (Root-Cause Fix):** On modern laptops using S0 Low Power Idle, calling standard OS Sleep freezes background Python timers and drops `WakeToRun` alarms on battery. Replaced with a **Hybrid AC / Battery Power Engine**:
  - **On AC Power (Plugged In):** Uses Display-Off standby (`SC_MONITORPOWER`) so timers never freeze and resets fire with zero boot delay.
  - **On Battery Power (DC):** Automatically switches to **Hibernate (`S4`, 0% battery drain)** and relies on motherboard-level RTC hardware alarms to physically boot the laptop back up before the quota resets.
- **Unattended Hibernate Dark-Screen & 2-Minute Re-Sleep Fix:** When Windows wakes from Hibernate via an RTC timer, it leaves the display off (causing ChatGPT Electron UI rendering to stall) and starts a hidden 2-minute unattended sleep timeout. Added `_nudge_wake()` to send a 1px mouse nudge (`mouse_event`) and acquire a system-only wake lock (`ES_CONTINUOUS | ES_SYSTEM_REQUIRED`) immediately upon wake.
- **15-Minute Post-Wake Re-Hibernate Guard:** Prevents the app from putting the laptop back into Hibernate if an RTC alarm wakes the machine 10 minutes ahead of a scheduled reset (`_POST_WAKE_GUARD_SEC = 900`).
- **Sticky Dual-Monitor Wake Lock Fix:** Eliminated `ES_DISPLAY_REQUIRED` and fixed `UInt32` `SetThreadExecutionState` handling so external/secondary monitors turn off cleanly instead of staying permanently lit.
- **Multi-Format 5-Hour & Weekly Quota Parser:** Expanded regex parsing to handle rolling 5-hour limits alongside multi-day Weekly limits (`Xd Yh` countdowns, 12h/24h clocks, and `Nov 20` / `20 November` date formats).
- **Strict System-Banner Detection:** Distinguishes genuine ChatGPT rate-limit banners from normal assistant replies that happen to mention usage limits, preventing false-positive locks.
- **Post-Send Verification & +15s Server Clock Buffer:** Waits 15 seconds past the target reset minute, submits `Continue`, verifies that the text actually leaves the composer input box, and auto-refreshes via a tab-switch ladder if the UI is still locked.
- **Material 3 Dashboard:** Real-time countdowns, sidebar conversation scanner and pinner, and hardware wake alarm auditing.

---

## Quick Start (Windows 10/11)
1. Clone this repository and create a virtual environment:
   - `git clone https://github.com/shin238123-coder/ChatGPT-Auto-Resume.git`
   - `cd ChatGPT-Auto-Resume`
   - `python -m venv .venv`
   - `.\.venv\Scripts\pip install -r requirements.txt`
2. Launch the app:
   - `.\.venv\Scripts\pythonw.exe main.py`
   - *(First run only: if Hibernate is disabled on your PC, approve the one-time Windows UAC prompt so the app can configure Hibernate, RTC wake timers, and wake-without-lock automatically.)*

---

## Credits & Acknowledgments
- **Original Concept & Base UIA Architecture:** Full credit and special thanks to **[MoELuaNMaT](https://github.com/MoELuaNMaT)**, creator of **[GPT_KeepGoing](https://github.com/MoELuaNMaT/GPT_KeepGoing)**, for the foundational Windows UI Automation (`uiautomation`) reader/actor architecture.
- **24/7 Unattended Engine, Auto-Provisioned Hybrid AC/Hibernate S4 Wake Orchestration, Post-Send Verification & Material 3 UI:** Built and extended by Shino Shibu.
