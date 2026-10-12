"""电脑状态悬浮监控 —— 程序入口。

运行（必须用 conda 的 agent 环境，勿动全局环境）：
    conda activate agent
    python main.py
或直接双击 run.bat。
"""
from __future__ import annotations

import os
import sys

# 依赖缺失时给出中文提示后退出
try:
    import psutil  # noqa: F401
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    print("缺少依赖，请在 agent 环境中安装：")
    print("    conda activate agent")
    print("    pip install -r requirements.txt")
    print(f"详情: {exc}")
    sys.exit(1)

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMessageBox

from app import config
from app.diskwatch import DiskWatch, human
from app.monitor import SystemMonitor
from app.overlay import OverlayWindow
from app.report_window import ReportWindow
from app.toast import show_toast
from app.tray import TrayIcon

_INSTANCE_KEY = "SysWatcher_LocalServer_v1"


def _single_instance_guard() -> QLocalServer | None:
    """防重复启动：已有实例在运行时返回 None。"""
    sock = QLocalSocket()
    sock.connectToServer(_INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.disconnectFromServer()
        return None
    QLocalServer.removeServer(_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(_INSTANCE_KEY)
    return server


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 托盘常驻：关窗口不退出

    if _single_instance_guard() is None:
        QMessageBox.information(None, config.APP_TITLE,
                                "程序已在运行中（看屏幕角落或托盘图标）。")
        return 0

    cfg = config.load()
    monitor = SystemMonitor(cfg)
    overlay = OverlayWindow(cfg)

    # ---- 接线：采样 -> 悬浮窗；告警 -> Toast ----
    # （v0.2 重构时这两行曾被漏掉，导致悬浮窗全部显示 0、告警失效，别再删）
    monitor.sampled.connect(overlay.update_data)
    monitor.alert.connect(show_toast)

    def toggle_overlay():
        if overlay.isVisible():
            overlay.hide()
            cfg["show_overlay"] = False
        else:
            overlay.show()
            cfg["show_overlay"] = True
        config.save(cfg)
        tray.refresh()

    # ---- C盘增长侦探 ----
    watch = DiskWatch(cfg)
    report_win = ReportWindow(watch, cfg)

    def open_report():
        report_win.show()
        report_win.raise_()
        report_win.activateWindow()

    def on_disk_report(rep: dict) -> None:
        if rep.get("rebuild") or rep.get("first"):
            action = "基线已重建" if rep.get("rebuild") else "首次扫描完成，基线已建立"
            body = (f"C盘{action}：用时 {rep['elapsed']:.0f} 秒，统计 "
                    f"{rep['files_total']:,} 个文件（{human(rep['size_total'])}）。"
                    "之后的扫描将显示各目录增长对比。")
        else:
            tops = rep.get("top_last") or []
            parts = [
                f"{os.path.basename(p.rstrip(chr(92))) or p} +{human(d)}"
                for p, d in tops[:2]
            ]
            body = f"C盘扫描完成（{rep['elapsed']:.0f} 秒）。本次增长："
            body += "；".join(parts) if parts else "基本无变化"
            drop = rep.get("free_delta_gb")
            if drop and drop >= 2:
                body += f"；剩余空间较上次少了 {drop:.1f}GB，详见C盘报告"
        show_toast("hint", body)

    watch.reportReady.connect(on_disk_report)

    def quit_all():
        monitor.stop()
        config.save(cfg)
        if watch.is_scanning():
            # 扫描中退出：先中止扫描（毫秒级响应），线程收尾后再退出
            pending = [True]

            def _quit():
                if pending[0]:
                    pending[0] = False
                    app.quit()

            watch.workerFinished.connect(_quit)
            watch.abort_scan()
        else:
            app.quit()

    tray = TrayIcon(overlay, cfg, on_toggle=toggle_overlay, on_quit=quit_all,
                    on_report=open_report)
    overlay.hideRequested.connect(toggle_overlay)
    overlay.quitRequested.connect(quit_all)
    overlay.reportRequested.connect(open_report)
    overlay.stateChanged.connect(tray.refresh)

    def on_click_through(on: bool) -> None:
        if on:
            show_toast("hint",
                       "已开启鼠标穿透：鼠标会直接穿过悬浮窗。\n"
                       "关闭方式：托盘图标右键 → 取消勾选“点击穿透”。")

    overlay.clickThroughChanged.connect(on_click_through)

    overlay.set_click_through(bool(cfg["click_through"]))
    overlay.place_default()
    if cfg["show_overlay"]:
        overlay.show()

    tray.show()
    monitor.start()
    try:
        return app.exec()
    finally:
        monitor.stop()


if __name__ == "__main__":
    sys.exit(main())
