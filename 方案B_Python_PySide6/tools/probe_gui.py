"""真实 GUI 环境探测：用 windows 平台插件（非 offscreen）跑真实 SystemMonitor，
验证 CPU/内存采样在完整 QApplication 事件循环下的数值（不开任何窗口）。

用法（agent env）: python tools/probe_gui.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import config
from app.monitor import SystemMonitor


def main() -> int:
    app = QApplication(sys.argv)
    print("platform:", QApplication.platformName())
    cfg = config.load()
    m = SystemMonitor(cfg)
    rows: list[tuple[float, float]] = []
    m.sampled.connect(lambda s: rows.append((s["cpu"], s["mem"])))
    m.start()
    QTimer.singleShot(5500, app.quit)
    app.exec()
    for i, (c, mm) in enumerate(rows, 1):
        print(f"tick {i:02d}  cpu={c:6.2f}%  mem={mm:5.1f}%")
    ok = bool(rows) and any(c > 0.0 for c, _ in rows)
    print("PROBE OK" if ok else "PROBE: all cpu zero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
