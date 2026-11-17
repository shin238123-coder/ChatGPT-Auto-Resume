# ChatGPT Auto Resume (24/7 Unattended Quota & Wake Manager)

An automated Windows desktop companion for the official ChatGPT Desktop app that monitors long-running agent and Codex sessions, tracks **5-Hour** and **Weekly** usage quotas in real time, manages display and system power states during idle periods, and automatically resumes your pinned conversation (`Continue`) the moment your rate limit resets.

## Key Features & Upgrades
- **Multi-Format Quota & Weekly Reset Parser:** Tracks rolling 5-hour limits and multi-day Weekly limits (`Xd Yh` countdowns, 12h/24h clocks, and `Nov 20` / `20 November` dates).
- **Post-Send Verification & +15s Server Clock Buffer:** Waits 15 seconds past the target reset minute, submits `Continue`, and verifies that the text actually leaves the composer input box (auto-refreshing via tab-switch ladder if the UI is still locked).
- **S0 Modern Standby & Dual-Display Power Management:** Enters low-power Display-Off standby without letting Windows S0 Modern Standby freeze background timers or hold sticky `ES_DISPLAY_REQUIRED` locks on external monitors.
- **Strict System-Banner Detection:** Distinguishes genuine ChatGPT rate-limit banners from assistant chat responses that discuss usage limits, preventing false-positive locks.
- **Material 3 Dashboard:** Real-time countdowns, sidebar conversation scanner and pinner, and hardware wake alarm auditing.

## Quick Start (Windows 10/11)
1. Clone this repository and create a virtual environment:
   - `git clone https://github.com/shin238123-coder/ChatGPT-Auto-Resume.git`
   - `cd ChatGPT-Auto-Resume`
   - `python -m venv .venv`
   - `.\.venv\Scripts\pip install -r requirements.txt`
2. Launch the app:
   - `.\.venv\Scripts\pythonw.exe main.py`

## Credits & Acknowledgments
- **Original Concept & Base UIA Architecture:** Full credit and thanks to the original creator of **GPT_KeepGoing** for the foundational Windows UI Automation reader/actor structure.
- **24/7 Unattended Engine, S0 Power/Wake Orchestration, Post-Send Verification & Material 3 UI:** Built by Shino Shibu.
