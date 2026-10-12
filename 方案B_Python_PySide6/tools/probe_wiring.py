"""接线探测：复刻 main() 里"采样→悬浮窗"的连线，验证数据真的流到悬浮窗。

防止再出现"各模块自身正常、但 main 忘了 connect"的回归
（v0.2 就发生过：CPU/MEM/C盘全部显示 0）。

用法（agent env）: python tools/probe_wiring.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import config
from app.monitor import SystemMonitor
from app.overlay import OverlayWindow
from app.toast import show_toast


def main() -> int:
    app = QApplication(sys.argv)
    cfg = config.load()
    monitor = SystemMonitor(cfg)
    overlay = OverlayWindow(cfg)

    # 与 main.py 保持一致的接线（改 main 的连线时同步改这里）
    monitor.sampled.connect(overlay.update_data)
    monitor.alert.connect(show_toast)

    monitor.start()
    QTimer.singleShot(4000, app.quit)
    app.exec()

    ok = (overlay.mem > 0.0
          and overlay.disk_free > 0.0
          and len(overlay._cpu_hist) == len(monitor.cpu_hist) > 0)
    print(f"overlay: cpu={overlay.cpu:.2f}% mem={overlay.mem:.1f}% "
          f"disk_free={overlay.disk_free:.1f}GB hist={len(overlay._cpu_hist)}")
    print("WIRING OK" if ok else "WIRING BROKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
