"""右下角 Toast 告警弹窗：无边框、半透明、置顶、不抢焦点、鼠标穿透。

打游戏时告警绝不打扰操作（WindowTransparentForInput + WA_ShowWithoutActivating），
显示 6 秒后自动淡出。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QTimer, QPropertyAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

_TITLES = {"memory": "内存即将耗尽", "disk": "C盘空间不足", "hint": "提示"}
_ACCENT = {"memory": QColor(255, 112, 67), "disk": QColor(102, 187, 106)}
_FALLBACK_ACCENT = QColor(255, 209, 128)

_BG = QColor(26, 30, 40, 242)
_FG = QColor(236, 239, 241)


class ToastWindow(QWidget):
    HOLD_MS = 6000

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._accent = _FALLBACK_ACCENT
        self._title = QLabel(self)
        self._title.setFont(QFont("Microsoft YaHei UI", 11, QFont.DemiBold))
        self._body = QLabel(self)
        self._body.setFont(QFont("Microsoft YaHei UI", 9))
        self._body.setWordWrap(True)
        self._title.setStyleSheet("background: transparent;")
        self._body.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 14, 18, 16)
        lay.setSpacing(4)
        lay.addWidget(self._title)
        lay.addWidget(self._body)

        self._anim_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_in.setDuration(220)
        self._anim_out = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim_out.setDuration(420)
        self._anim_out.finished.connect(self.hide)

        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._fade_out)

    # ------------------------------------------------------------------
    def popup(self, level: str, text: str) -> None:
        self._accent = _ACCENT.get(level, _FALLBACK_ACCENT)
        self._title.setText(_TITLES.get(level, "提醒"))
        self._title.setStyleSheet(
            f"background: transparent; color: {self._accent.name()};"
        )
        self._body.setText(text)
        self._body.setStyleSheet(f"background: transparent; color: {_FG.name()};")
        self.adjustSize()
        self.resize(max(self.width(), 360), self.height())

        sg = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.move(sg.right() - self.width() - 24, sg.bottom() - self.height() - 28)

        self._anim_out.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._anim_in.stop()
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.start()
        self._hold.start(self.HOLD_MS)

    def _fade_out(self) -> None:
        self._anim_in.stop()
        self._anim_out.setStartValue(self.windowOpacity())
        self._anim_out.setEndValue(0.0)
        self._anim_out.start()

    # ------------------------------------------------------------------
    def paintEvent(self, _) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.fillPath(path, _BG)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.drawPath(path)
        # 左侧彩色警示条
        p.setClipPath(path)
        p.fillRect(0, 0, 6, self.height(), self._accent)


_toast: ToastWindow | None = None


def show_toast(level: str, text: str) -> None:
    """模块级入口：全程只有一个 Toast 实例，重复告警会刷新内容与倒计时。"""
    global _toast
    if _toast is None:
        _toast = ToastWindow()
    _toast.popup(level, text)
