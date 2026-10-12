"""桌面悬浮监控窗：无边框、半透明、置顶、可拖动、可折叠、可点击穿透。

快捷操作：
  左键拖动        移动位置（位置会保存到 config.json）
  左键双击        折叠 / 展开迷你条与完整面板
  右键            菜单（折叠、点击穿透、背景不透明度、隐藏、退出）
  Ctrl + 滚轮     调节背景不透明度（只影响背景，文字/占用条不变）

点击穿透实现说明：Windows 下直接改原生扩展样式 WS_EX_TRANSPARENT，
不销毁重建窗口。旧版用 Qt 窗口标志切换会让半透明窗口经历"销毁-重建"，
重建后不再渲染 —— 这就是开启穿透后悬浮窗消失的原因。
"""
from __future__ import annotations

import ctypes
from collections import deque

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QGuiApplication, QColor, QFont, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMenu,
                               QSlider, QWidget, QWidgetAction)

from . import config

_FG = QColor(232, 236, 241)
_DIM = QColor(156, 164, 176, 220)
_GRID = QColor(255, 255, 255, 16)
_CPU = QColor(79, 195, 247)
_MEM = QColor(255, 183, 77)
_MEM_HOT = QColor(239, 83, 80)
_DISK = QColor(129, 199, 132)

_FONT = QFont("Microsoft YaHei UI", 9)
_FONT_SMALL = QFont("Microsoft YaHei UI", 8)
_FONT_TINY = QFont("Microsoft YaHei UI", 7)

COMPACT_SIZE = (272, 84)
EXPANDED_SIZE = (320, 216)

_BG_RGB = (16, 20, 28)          # 背景色（alpha 由"背景不透明度"控制）
_BG_ALPHA_MAX = 205             # 不透明度 100% 时的背景 alpha（原版观感）

# ---- Windows 原生"点击穿透"（WS_EX_TRANSPARENT）----
_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000


def _win_set_click_through(hwnd: int, on: bool) -> None:
    """直接改窗口扩展样式，不销毁重建窗口：切换无闪烁、不消失。

    关闭时只清 TRANSPARENT 位、保留 LAYERED 位（半透明渲染需要它）。
    """
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    if on:
        style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
    else:
        style &= ~_WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)


class OverlayWindow(QWidget):
    stateChanged = Signal()          # 形态变化后发出，托盘用于刷新勾选状态
    hideRequested = Signal()         # 右键菜单选择"隐藏"
    reportRequested = Signal()       # 右键菜单选择"C盘增长报告"
    quitRequested = Signal()         # 右键菜单选择"退出"
    clickThroughChanged = Signal(bool)  # 点击穿透开关变化（main 用于弹提示）

    def __init__(self, cfg: dict):
        super().__init__(None)
        self.cfg = cfg
        self._compact = bool(cfg["compact"])
        self._history_len = max(10, int(cfg["history_len"]))
        self._cpu_hist: deque[float] = deque(maxlen=self._history_len)
        self._mem_hist: deque[float] = deque(maxlen=self._history_len)

        self.cpu = 0.0
        self.mem = 0.0
        self.mem_used = 0.0
        self.mem_total = 0.0
        self.swap = 0.0
        self.disk_free = 0.0
        self.disk_total = 0.0
        self.drive = "C:"

        self._drag_pos: QPoint | None = None
        self._bg_opacity = min(max(float(cfg.get("bg_opacity", 0.8)), 0.0), 1.0)
        self._save_timer = QTimer(self)  # 滑条拖动时防抖保存
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: config.save(self.cfg))

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(*(COMPACT_SIZE if self._compact else EXPANDED_SIZE))

    # ---------------- 数据入口（由 main 接到 monitor.sampled） ----------------
    def update_data(self, snap: dict) -> None:
        self.cpu = snap["cpu"]
        self.mem = snap["mem"]
        self.mem_used = snap["mem_used_gb"]
        self.mem_total = snap["mem_total_gb"]
        self.swap = snap["swap"]
        self.disk_free = snap["disk_free_gb"]
        self.disk_total = snap["disk_total_gb"]
        self.drive = snap["drive"]
        self._cpu_hist.append(self.cpu)
        self._mem_hist.append(self.mem)
        self.update()  # 触发重绘

    # ---------------- 行为 ----------------
    def place_default(self) -> None:
        """按配置落位；overlay_x = -1 表示自动停靠主屏右上角。"""
        x = int(self.cfg["overlay_x"])
        y = int(self.cfg["overlay_y"])
        if x < 0:
            sg = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            x = sg.right() - self.width() - 16
        self.move(max(x, 0), max(y, 0))

    def toggle_compact(self) -> None:
        self._compact = not self._compact
        self.cfg["compact"] = self._compact
        self.resize(*(COMPACT_SIZE if self._compact else EXPANDED_SIZE))
        config.save(self.cfg)
        self.stateChanged.emit()
        self.update()

    def set_click_through(self, on: bool) -> None:
        """开启后鼠标会穿过窗口（打游戏不挡操作），从托盘菜单可关。"""
        on = bool(on)
        self.cfg["click_through"] = on
        if QGuiApplication.platformName() == "windows":
            _win_set_click_through(int(self.winId()), on)
        else:
            # 非 Windows 平台的兜底（本应用主要面向 Windows）
            self.setWindowFlag(Qt.WindowTransparentForInput, on)
            if self.isVisible() or not on:
                self.show()
        config.save(self.cfg)
        self.stateChanged.emit()
        self.clickThroughChanged.emit(on)

    def set_bg_opacity(self, v: float) -> None:
        """调节背景不透明度（0~1），只影响背景与边框，文字/占用条不变。"""
        v = min(max(float(v), 0.0), 1.0)
        if abs(v - self._bg_opacity) < 0.001:
            return
        self._bg_opacity = v
        self.cfg["bg_opacity"] = v
        self._save_timer.start(600)  # 拖动结束后 0.6s 落盘
        self.update()

    def opacity_submenu(self, parent) -> QMenu:
        """'背景不透明度'子菜单：内嵌滑条，实时预览。"""
        menu = QMenu("背景不透明度", parent)
        box = QWidget(menu)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(8, 2, 8, 2)
        slider = QSlider(Qt.Horizontal, box)
        slider.setRange(0, 100)
        slider.setValue(int(round(self._bg_opacity * 100)))
        slider.setFixedWidth(150)
        label = QLabel(f"{slider.value()}%", box)
        label.setFixedWidth(34)

        def on_change(v: int) -> None:
            label.setText(f"{v}%")
            self.set_bg_opacity(v / 100.0)

        slider.valueChanged.connect(on_change)
        lay.addWidget(slider)
        lay.addWidget(label)
        act = QWidgetAction(menu)
        act.setDefaultWidget(box)
        menu.addAction(act)
        return menu

    # ---------------- 事件 ----------------
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        # 显示/隐藏周期里 Qt 可能重置窗口样式，重新补上点击穿透
        if (self.cfg.get("click_through")
                and QGuiApplication.platformName() == "windows"):
            _win_set_click_through(int(self.winId()), True)

    def wheelEvent(self, e) -> None:  # noqa: N802
        if e.modifiers() & Qt.ControlModifier:
            step = 0.05 if e.angleDelta().y() > 0 else -0.05
            self.set_bg_opacity(self._bg_opacity + step)
            e.accept()
        else:
            e.ignore()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag_pos is not None:
            self._drag_pos = None
            self.cfg["overlay_x"] = self.x()
            self.cfg["overlay_y"] = self.y()
            config.save(self.cfg)
            e.accept()

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.toggle_compact()
            e.accept()

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        a_toggle = menu.addAction("展开完整面板" if self._compact else "折叠为迷你条")
        a_toggle.triggered.connect(self.toggle_compact)
        a_through = menu.addAction(
            "关闭点击穿透" if self.cfg["click_through"]
            else "开启点击穿透（鼠标穿过窗口）"
        )
        a_through.triggered.connect(
            lambda: self.set_click_through(not self.cfg["click_through"])
        )
        a_report = menu.addAction("C盘增长报告")
        a_report.triggered.connect(self.reportRequested.emit)
        menu.addSeparator()
        menu.addMenu(self.opacity_submenu(menu))
        menu.addSeparator()
        a_hide = menu.addAction("隐藏悬浮窗（托盘可找回）")
        a_hide.triggered.connect(self.hideRequested.emit)
        a_quit = menu.addAction("退出")
        a_quit.triggered.connect(self.quitRequested.emit)
        menu.exec(e.globalPos())

    # ---------------- 绘制 ----------------
    def _mem_color(self) -> QColor:
        return _MEM_HOT if self.mem >= 90 else _MEM

    @staticmethod
    def _fmt_pct(v: float) -> str:
        # 低占用时保留一位小数，避免 0.4% 被显示成 "0%" 造成"CPU一直0%"的误判
        return f"{v:.1f}%" if v < 10 else f"{v:.0f}%"

    def paintEvent(self, _) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        bg_alpha = int(_BG_ALPHA_MAX * self._bg_opacity)
        border_alpha = int(26 * self._bg_opacity)
        p.fillPath(path, QColor(*_BG_RGB, bg_alpha))
        p.setPen(QPen(QColor(255, 255, 255, border_alpha), 1))
        p.drawPath(path)
        if self._compact:
            self._paint_compact(p)
        else:
            self._paint_expanded(p)

    def _bar(self, p: QPainter, x: float, y: float, w: float, h: float, pct: float,
             color: QColor, label: str, value_text: str, hot: bool = False) -> None:
        p.setFont(_FONT_SMALL)
        p.setPen(QPen(_DIM))
        p.drawText(QRectF(x, y, 36, h), Qt.AlignVCenter | Qt.AlignLeft, label)
        bx, bw = x + 40, w - 86
        track = QRectF(bx, y + (h - 10) / 2, bw, 10)
        tp = QPainterPath()
        tp.addRoundedRect(track, 5, 5)
        p.fillPath(tp, QColor(255, 255, 255, 34))
        if pct > 0:
            fill_w = min(max(bw * pct / 100.0, 6), bw)
            fp = QPainterPath()
            fp.addRoundedRect(QRectF(bx, track.y(), fill_w, 10), 5, 5)
            p.fillPath(fp, color)
        p.setPen(QPen(_MEM_HOT if hot else _FG))
        p.setFont(_FONT_SMALL)
        p.drawText(QRectF(bx + bw + 6, y, 40, h), Qt.AlignVCenter | Qt.AlignLeft, value_text)

    def _paint_compact(self, p: QPainter) -> None:
        w = self.width()
        self._bar(p, 14, 8, w - 28, 24, self.cpu, _CPU, "CPU", self._fmt_pct(self.cpu))
        self._bar(p, 14, 36, w - 28, 24, self.mem, self._mem_color(), "MEM",
                  f"{self.mem:.0f}%", hot=self.mem >= 90)
        p.setFont(_FONT_TINY)
        p.setPen(QPen(_DIM))
        p.drawText(QRectF(14, 62, w - 28, 16), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{self.drive}盘剩余 {self.disk_free:.1f} GB")

    def _paint_expanded(self, p: QPainter) -> None:
        w = self.width()
        self._bar(p, 14, 10, w - 28, 24, self.cpu, _CPU, "CPU", self._fmt_pct(self.cpu))
        self._bar(p, 14, 38, w - 28, 24, self.mem, self._mem_color(), "MEM",
                  f"{self.mem:.0f}%", hot=self.mem >= 90)

        # ---- 曲线区 ----
        cur = QRectF(14, 68, w - 28, 92)
        p.setPen(QPen(_GRID, 1))
        for v in (0, 25, 50, 75, 100):
            y = cur.top() + cur.height() * v / 100.0
            p.drawLine(QPointF(cur.left(), y), QPointF(cur.right(), y))
        self._plot(p, self._cpu_hist, _CPU, cur)
        self._plot(p, self._mem_hist, self._mem_color(), cur)

        mem_color = self._mem_color()
        p.setFont(_FONT_TINY)
        p.setPen(QPen(_CPU))
        p.setBrush(_CPU)
        p.drawEllipse(QPointF(cur.left() + 6, cur.top() + 8), 3, 3)
        p.drawText(QPointF(cur.left() + 12, cur.top() + 11), "CPU")
        p.setPen(QPen(mem_color))
        p.setBrush(mem_color)
        p.drawEllipse(QPointF(cur.left() + 44, cur.top() + 8), 3, 3)
        p.drawText(QPointF(cur.left() + 50, cur.top() + 11), "MEM")
        p.setPen(QPen(_DIM))
        p.drawText(QRectF(cur.left(), cur.top(), cur.width(), 14),
                   Qt.AlignRight | Qt.AlignTop,
                   f"{self.mem_used:.1f} / {self.mem_total:.0f} GB")

        # ---- 磁盘 ----
        used_pct = 0.0
        if self.disk_total > 0:
            used_pct = (1 - self.disk_free / self.disk_total) * 100
        p.setFont(_FONT_TINY)
        p.setPen(QPen(_DIM))
        p.drawText(QRectF(14, 170, w - 28, 14), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{self.drive}盘  已用 {used_pct:.0f}%")
        p.drawText(QRectF(14, 170, w - 28, 14), Qt.AlignVCenter | Qt.AlignRight,
                   f"剩 {self.disk_free:.1f} / {self.disk_total:.0f} GB")
        track = QRectF(14, 188, w - 28, 8)
        tp = QPainterPath()
        tp.addRoundedRect(track, 4, 4)
        p.fillPath(tp, QColor(255, 255, 255, 34))
        fw = min(max((w - 28) * used_pct / 100.0, 4), w - 28)
        fp = QPainterPath()
        fp.addRoundedRect(QRectF(14, track.y(), fw, 8), 4, 4)
        p.fillPath(fp, _DISK if used_pct < 90 else _MEM_HOT)

    def _plot(self, p: QPainter, hist: deque, color: QColor, rect: QRectF) -> None:
        n = len(hist)
        if n < 2:
            return
        span = self._history_len - 1
        path = QPainterPath()
        for i, v in enumerate(hist):
            x = rect.left() + rect.width() * i / span
            y = rect.bottom() - rect.height() * max(0.0, min(100.0, v)) / 100.0
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(color, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
