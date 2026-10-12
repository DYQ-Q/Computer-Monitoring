"""系统托盘：显示/隐藏悬浮窗、折叠、点击穿透、开机自启、退出。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from . import autostart, config


def make_icon() -> QIcon:
    """程序图标：深色圆角底 + 心电脉搏折线，代码绘制、无需外部图片。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(6, 6, 52, 52), 14, 14)
    p.fillPath(path, QColor(24, 30, 42))
    pen = QPen(QColor(79, 195, 247), 5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    pts = [(14, 36), (24, 36), (29, 22), (35, 46), (40, 36), (50, 36)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        p.drawLine(x1, y1, x2, y2)
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, overlay, cfg: dict, on_toggle, on_quit, on_report):
        super().__init__(make_icon())
        self.overlay = overlay
        self.cfg = cfg
        self._on_toggle = on_toggle
        self.setToolTip(config.APP_TITLE)

        self.menu = QMenu()
        self.act_show = QAction(self.menu)
        self.act_show.triggered.connect(self._on_toggle)

        self.act_compact = QAction("折叠为迷你条", self.menu, checkable=True,
                                   checked=bool(cfg["compact"]))
        self.act_compact.triggered.connect(self._on_compact)

        self.act_through = QAction("点击穿透（鼠标穿过窗口）", self.menu, checkable=True,
                                   checked=bool(cfg["click_through"]))
        self.act_through.triggered.connect(self._on_through)

        self.act_autorun = QAction("开机自启", self.menu, checkable=True,
                                   checked=autostart.is_enabled())
        self.act_autorun.triggered.connect(self._on_autorun)

        act_about = QAction("关于 / 使用说明", self.menu)
        act_about.triggered.connect(self._about)
        act_quit = QAction("退出", self.menu)
        act_quit.triggered.connect(on_quit)

        self.menu.addAction(self.act_show)
        act_report = QAction("C盘增长报告", self.menu)
        act_report.triggered.connect(on_report)
        self.menu.addAction(act_report)
        self.menu.addSeparator()
        self.menu.addAction(self.act_compact)
        self.menu.addAction(self.act_through)
        self.menu.addMenu(self.overlay.opacity_submenu(self.menu))
        self.menu.addAction(self.act_autorun)
        self.menu.addSeparator()
        self.menu.addAction(act_about)
        self.menu.addAction(act_quit)
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_activated)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.act_show.setText("隐藏悬浮窗" if self.overlay.isVisible() else "显示悬浮窗")
        self.act_compact.setChecked(bool(self.cfg["compact"]))
        self.act_through.setChecked(bool(self.cfg["click_through"]))

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._on_toggle()

    def _on_compact(self, checked: bool) -> None:
        if bool(self.cfg["compact"]) != checked:
            self.overlay.toggle_compact()
        self.refresh()

    def _on_through(self, checked: bool) -> None:
        self.overlay.set_click_through(checked)
        self.refresh()

    def _on_autorun(self, checked: bool) -> None:
        ok = autostart.set_enabled(checked)
        if not ok:
            self.act_autorun.setChecked(not checked)
            self.showMessage(config.APP_TITLE, "开机自启设置失败，请查看控制台输出。",
                             QSystemTrayIcon.Warning, 4000)

    def _about(self) -> None:
        QMessageBox.information(
            None, config.APP_TITLE,
            f"{config.APP_TITLE}\n\n"
            "悬浮窗：左键拖动 / 左键双击折叠 / 右键菜单\n"
            "点击穿透：开启后鼠标直接穿过悬浮窗，从托盘菜单可关闭\n"
            "告警：内存占用超过阈值、C盘剩余空间不足时，右下角弹 Toast\n"
            "配置文件：项目根目录 config.json（可改阈值后重启生效）\n",
        )
