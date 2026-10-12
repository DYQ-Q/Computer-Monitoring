"""C盘增长报告窗口：当前用量 + 增长排行 + 手动扫描控制。"""
from __future__ import annotations

import os
import time

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from . import config
from .diskwatch import _GB, DiskWatch, human


class ReportWindow(QWidget):
    def __init__(self, watch: DiskWatch, cfg: dict):
        super().__init__(None, Qt.Window)
        self._watch = watch
        self._cfg = cfg
        self.setWindowTitle("C盘增长报告")
        self.resize(800, 540)

        self.lbl_disk = QLabel(self)
        self.lbl_disk.setStyleSheet("font-weight:600; font-size:13px;")
        self.lbl_info = QLabel(self)
        self.lbl_sys = QLabel(self)

        self.btn_scan = QPushButton("立即扫描（与上次对比）", self)
        self.btn_scan.clicked.connect(self._on_scan)
        self.btn_rebuild = QPushButton("重建基线", self)
        self.btn_rebuild.clicked.connect(self._on_rebuild)
        self.chk_deep = QCheckBox("深度扫描（含 Windows / Program Files，较慢）", self)
        self.chk_deep.setChecked(bool(cfg.get("diskwatch_deep_scan", False)))
        self.chk_deep.toggled.connect(self._on_deep_toggled)

        self.lbl_status = QLabel(self)
        self.lbl_note = QLabel(self)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet("color:#c0392b;")

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["路径", "本次增长", "距基线增长", "文件数"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl_disk)
        lay.addWidget(self.lbl_info)
        lay.addWidget(self.lbl_sys)
        row = QHBoxLayout()
        row.addWidget(self.btn_scan)
        row.addWidget(self.btn_rebuild)
        row.addWidget(self.chk_deep)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self.lbl_status)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.lbl_note)

        watch.progress.connect(self.lbl_status.setText)
        watch.reportReady.connect(lambda _rep: self.apply_report())
        self._btn_timer = QTimer(self)
        self._btn_timer.setInterval(400)
        self._btn_timer.timeout.connect(self._sync_buttons)
        self._btn_timer.start()
        self.refresh_summary()

    # ---------------- UI 状态 ----------------
    def set_status(self, msg: str) -> None:
        self.lbl_status.setText(msg)

    def _sync_buttons(self) -> None:
        busy = self._watch.is_scanning()
        self.btn_scan.setEnabled(not busy)
        self.btn_rebuild.setEnabled(not busy)

    def _on_deep_toggled(self, on: bool) -> None:
        self._cfg["diskwatch_deep_scan"] = bool(on)
        config.save(self._cfg)

    def _on_scan(self) -> None:
        if not self._watch.start_scan(deep=self.chk_deep.isChecked()):
            self.lbl_status.setText("已有扫描在进行中…")

    def _on_rebuild(self) -> None:
        ret = QMessageBox.question(
            self, "重建基线",
            "把当前状态记为新的基线？\n之后的增长都相对这个基线计算。",
        )
        if ret == QMessageBox.Yes:
            self._watch.start_scan(deep=self.chk_deep.isChecked(), rebuild=True)

    # ---------------- 数据刷新 ----------------
    def refresh_summary(self) -> None:
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            du = psutil.disk_usage(drive)
            self.lbl_disk.setText(
                f"C盘：共 {human(du.total)} | 已用 {human(du.used)}"
                f"（{du.percent:.0f}%）| 剩余 {human(du.free)}"
            )
        except OSError:
            self.lbl_disk.setText("C盘：读取失败")
        last = self._watch.store.get("last")
        if last:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last["time"]))
            self.lbl_info.setText(
                f"上次扫描：{t}（每 "
                f"{self._cfg.get('diskwatch_interval_hours', 6)} 小时自动扫描一次，"
                "也可手动扫描）"
            )
        else:
            self.lbl_info.setText(
                "尚未扫描：启动后约 1 分钟会自动建立基线，或现在点“立即扫描”。"
            )
        rep = self._watch.last_report
        sysfiles = rep.get("system_files") if rep else None
        if sysfiles:
            self.lbl_sys.setText(
                "系统文件（不计入增长排行）："
                + "，".join(f"{n} {human(s)}" for n, s in sysfiles)
            )
        else:
            self.lbl_sys.setText("")

    def apply_report(self) -> None:
        self.refresh_summary()
        rep = self._watch.last_report
        if not rep:
            return

        skipped = rep.get("skipped") or []
        if skipped:
            self.lbl_note.setText(
                f"有 {len(skipped)} 个目录因权限无法读取已自动跳过"
                f"（如：{skipped[0]}）。以管理员身份运行可覆盖更多系统目录。"
            )
        else:
            self.lbl_note.setText("")

        tops = rep.get("top_last") or []
        basemap = dict(rep.get("top_baseline") or [])
        lastmap = dict(tops)
        ordered = [p for p, _ in tops]
        for p in basemap:
            if p not in lastmap:
                ordered.append(p)

        last_dirs = self._watch.store.get("last", {}).get("dirs", {})
        self.table.setRowCount(len(ordered))
        for i, path in enumerate(ordered):
            d_last = lastmap.get(path)
            d_base = basemap.get(path)
            files = last_dirs.get(path, [0, 0])[1]
            vals = [
                path,
                f"+{human(d_last)}" if d_last is not None else "—",
                f"+{human(d_base)}" if d_base is not None else "—",
                f"{files:,}",
            ]
            for j, text in enumerate(vals):
                item = QTableWidgetItem(text)
                if j > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, item)

        if rep.get("first") or rep.get("rebuild"):
            self.lbl_status.setText(
                f"基线已建立（用时 {rep['elapsed']:.0f} 秒，统计 "
                f"{rep['files_total']:,} 个文件）：下次扫描后显示增长对比。"
            )
        elif not ordered:
            self.lbl_status.setText(
                f"与上次扫描相比基本无变化（用时 {rep['elapsed']:.0f} 秒）。"
            )
        else:
            self.lbl_status.setText(
                f"扫描完成（用时 {rep['elapsed']:.0f} 秒，统计 "
                f"{rep['files_total']:,} 个文件），按增长排序如下："
            )

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.refresh_summary()
        self.apply_report()
