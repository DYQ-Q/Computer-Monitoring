"""离屏冒烟测试：不弹真实窗口，验证 采样 -> 曲线 -> 告警 -> Toast 全链路逻辑。

用法（agent 环境，在 方案B_Python_PySide6 目录下）：
    python tools/smoke_test.py
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
    # 测试参数：阈值降到 0.1%、持续 0 秒 -> 第一个采样就应触发内存告警
    cfg["memory_alert_threshold"] = 0.1
    cfg["memory_alert_hold_seconds"] = 0
    cfg["interval_ms"] = 300

    monitor = SystemMonitor(cfg)
    overlay = OverlayWindow(cfg)
    samples: list[dict] = []
    alerts: list[tuple[str, str]] = []

    def on_sample(s: dict) -> None:
        samples.append(s)
        overlay.update_data(s)

    monitor.sampled.connect(on_sample)
    monitor.alert.connect(lambda lv, tx: alerts.append((lv, tx)))
    monitor.start()

    def check() -> None:
        print(f"样本数: {len(samples)}  cpu_hist: {len(monitor.cpu_hist)}  "
              f"mem_hist: {len(monitor.mem_hist)}")
        if samples:
            s = samples[-1]
            print(f"最新: CPU {s['cpu']:.1f}%  MEM {s['mem']:.1f}%  "
                  f"{s['drive']}盘剩余 {s['disk_free_gb']:.1f} GB")
        for lv, tx in alerts:
            print(f"告警[{lv}]: {tx}")
        show_toast("memory", "冒烟测试 Toast（离屏模式不显示窗口，仅验证逻辑）")
        QTimer.singleShot(600, app.quit)

    QTimer.singleShot(1500, check)
    app.exec()

    ok = bool(samples) and bool(alerts) and len(monitor.cpu_hist) == len(samples)
    print("SMOKE OK" if ok else "SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
