"""CPU sampling diagnosis: compare psutil.cpu_percent vs manual cpu_times delta.

Mimics the app exactly: prime at init, then QTimer at 1000ms.
ASCII-only output to avoid console codepage mojibake.

Usage (agent env): python tools/diag_cpu.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil
from PySide6.QtCore import QCoreApplication, QTimer

TIME_FIELDS = ("user", "system", "idle", "interrupt", "dpc")


def manual_pct(state):
    t = psutil.cpu_times()
    total = sum(getattr(t, f, 0.0) for f in TIME_FIELDS)
    busy = total - getattr(t, "idle", 0.0)
    if state["last"] is None:
        state["last"] = (busy, total)
        return None
    d_busy = busy - state["last"][0]
    d_total = total - state["last"][1]
    state["last"] = (busy, total)
    if d_total <= 0:
        return None
    return max(0.0, min(100.0, d_busy / d_total * 100.0))


def main():
    print(f"psutil {psutil.__version__}  python {sys.version.split()[0]}")
    app = QCoreApplication(sys.argv)
    state = {"last": None}
    n = [0]

    def tick():
        n[0] += 1
        a = psutil.cpu_percent(interval=None)
        m = manual_pct(state)
        a_str = f"{a:6.2f}" if a is not None else "   n/a"
        m_str = f"{m:6.2f}" if m is not None else "   n/a"
        t = psutil.cpu_times()
        print(f"tick {n[0]:02d}  psutil={a_str}%  manual={m_str}%  "
              f"(u={t.user:.0f} s={t.system:.0f} idle={t.idle:.0f})")
        if n[0] >= 8:
            app.quit()

    psutil.cpu_percent(interval=None)  # prime, same as the app does
    manual_pct(state)                  # prime
    tm = QTimer()
    tm.setInterval(1000)
    tm.timeout.connect(tick)
    tm.start()
    app.exec()


if __name__ == "__main__":
    main()
