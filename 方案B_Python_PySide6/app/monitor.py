"""系统状态采样：CPU / 内存 / C盘，附带阈值告警（内存爆满提醒是核心功能）。

用 QTimer 在主线程轮询 psutil（单次采样 <5ms，不卡 UI）。

CPU 占用说明：不用 psutil.cpu_percent(interval=None)（部分 Windows 环境
下它会持续返回 0），改为每拍对 psutil.cpu_times() 做差值——busy 增量 /
总增量，原理相同但结果稳定。
"""
from __future__ import annotations

import os
import time
from collections import deque

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

_GB = 1024 ** 3

# Windows 的 cpu_times 字段（user/system/idle/interrupt/dpc）；
# 其他平台字段名不同，用 getattr 兜底，不影响本应用（面向 Windows）。
_TIME_FIELDS = ("user", "system", "idle", "interrupt", "dpc")


class SystemMonitor(QObject):
    sampled = Signal(dict)      # 每个采样周期发出一次快照
    alert = Signal(str, str)    # (级别, 文案) 级别: "memory" / "disk"

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.cpu_hist: deque[float] = deque(maxlen=int(cfg["history_len"]))
        self.mem_hist: deque[float] = deque(maxlen=int(cfg["history_len"]))

        self._last_times: tuple[float, float] | None = None  # (busy, total)
        self._mem_high_since: float | None = None
        self._last_mem_alert = 0.0
        self._last_disk_alert = 0.0
        self._drive = os.environ.get("SystemDrive", "C:")

        self._timer = QTimer(self)
        self._timer.setInterval(max(200, int(cfg["interval_ms"])))
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # ------------------------------------------------------------------
    def _cpu_percent(self) -> float | None:
        """对 cpu_times 做差值计算 CPU 占用；首拍返回 None（还在建立基准）。"""
        t = psutil.cpu_times()
        total = sum(getattr(t, f, 0.0) for f in _TIME_FIELDS)
        busy = total - getattr(t, "idle", 0.0)
        if self._last_times is None:
            self._last_times = (busy, total)
            return None
        d_busy = busy - self._last_times[0]
        d_total = total - self._last_times[1]
        self._last_times = (busy, total)
        if d_total <= 0:
            return None
        return max(0.0, min(100.0, d_busy / d_total * 100.0))

    def _tick(self) -> None:
        cpu = self._cpu_percent()
        if cpu is None:
            cpu = self.cpu_hist[-1] if self.cpu_hist else 0.0
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        try:
            du = psutil.disk_usage(self._drive + "\\")
            disk_free_gb = du.free / _GB
            disk_total_gb = du.total / _GB
        except OSError:
            disk_free_gb = disk_total_gb = 0.0

        snap = {
            "time": time.time(),
            "cpu": cpu,
            "mem": vm.percent,
            "mem_used_gb": (vm.total - vm.available) / _GB,
            "mem_total_gb": vm.total / _GB,
            "swap": sw.percent,
            "disk_free_gb": disk_free_gb,
            "disk_total_gb": disk_total_gb,
            "drive": self._drive,
        }
        self.cpu_hist.append(cpu)
        self.mem_hist.append(vm.percent)
        self.sampled.emit(snap)
        self._check_alerts(snap)

    # ------------------------------------------------------------------
    def _check_alerts(self, s: dict) -> None:
        now = float(s["time"])

        # ---- 内存告警（核心场景：爆内存前提醒，防卡顿/闪退）----
        thr = float(self.cfg["memory_alert_threshold"])
        hold = float(self.cfg["memory_alert_hold_seconds"])
        cooldown = float(self.cfg["memory_alert_cooldown_seconds"])
        if s["mem"] >= thr:
            if self._mem_high_since is None:
                self._mem_high_since = now
            held = now - self._mem_high_since
            if held >= hold and now - self._last_mem_alert >= cooldown:
                self._last_mem_alert = now
                free_gb = s["mem_total_gb"] - s["mem_used_gb"]
                self.alert.emit(
                    "memory",
                    f"内存占用 {s['mem']:.0f}% 已持续 {held:.0f} 秒"
                    f"（可用仅 {free_gb:.1f} GB）。程序可能开始卡顿甚至闪退，"
                    "建议关掉吃内存的应用。",
                )
        else:
            self._mem_high_since = None

        # ---- C盘剩余空间告警 ----
        min_gb = float(self.cfg["disk_alert_min_gb"])
        disk_cd = float(self.cfg["disk_alert_cooldown_seconds"])
        if 0 < s["disk_free_gb"] <= min_gb and now - self._last_disk_alert >= disk_cd:
            self._last_disk_alert = now
            self.alert.emit(
                "disk",
                f"{s['drive']}盘 剩余空间仅 {s['disk_free_gb']:.1f} GB，"
                "注意清理，否则系统可能变卡。",
            )
