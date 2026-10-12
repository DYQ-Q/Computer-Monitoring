"""C盘增长侦探：定时快照 + 差值分析，回答"C盘变少了，是谁吃的"。

原理：每次扫描记录各目录聚合体积（快照），与上次/基线对比得出增长排行。
普通用户权限即可运行；快照保存在 data/snapshot.json。

差值报告的两个维度：
- top_last：本次扫描相对上一次的增长（"最近谁在涨"）
- top_baseline：相对基线的累计增长（"这段时间谁涨得最多"）
top_growth 会把"已被祖先目录覆盖"的行去重，避免父目录和子目录重复刷屏。
"""
from __future__ import annotations

import json
import os
import tempfile
import time

import psutil
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .scanner import ScanAborted, build_roots, scan_roots, system_files_info

_GB = 1024 ** 3

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "data")
SNAP_FILE = os.path.join(DATA_DIR, "snapshot.json")


# ---------------- 快照存取 ----------------
def _load_store() -> dict:
    try:
        with open(SNAP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("baseline", None)
            data.setdefault("last", None)
            return data
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[diskwatch] 快照读取失败: {exc}")
    return {"baseline": None, "last": None}


def _save_store(store: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, SNAP_FILE)
    except Exception as exc:  # noqa: BLE001
        print(f"[diskwatch] 快照保存失败: {exc}")


# ---------------- 差值计算 ----------------
def diff_snapshots(old: dict | None, new: dict) -> dict[str, int]:
    """返回 {路径: 增长字节}（只保留正增长；新目录按全量计）。"""
    if not old:
        return {}
    old_dirs = old.get("dirs", {})
    out: dict[str, int] = {}
    for path, (size, _files) in new.get("dirs", {}).items():
        prev = old_dirs.get(path)
        if prev is None:
            out[path] = size
        elif size - prev[0] > 0:
            out[path] = size - prev[0]
    return out


def top_growth(deltas: dict[str, int], topn: int = 15) -> list[tuple[str, int]]:
    """按增长排序，并去掉"已被祖先覆盖"的行（祖先增长 >= 自己时不再单列）。"""
    rows = sorted(deltas.items(), key=lambda kv: -kv[1])
    kept: list[tuple[str, int]] = []
    for path, d in rows:
        covered = any(
            path.startswith(k.rstrip("\\") + "\\") and kd >= d
            for k, kd in kept
        )
        if not covered:
            kept.append((path, d))
        if len(kept) >= topn:
            break
    return kept


def human(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------- 后台扫描线程 ----------------
class _ScanWorker(QThread):
    progress = Signal(str)
    doneOk = Signal(object, float)   # (ScanResult, 用时秒)
    aborted = Signal()

    def __init__(self, deep: bool, parent=None):
        super().__init__(parent)
        self._deep = deep

    def run(self) -> None:
        t0 = time.time()
        try:
            res = scan_roots(build_roots(deep=self._deep), max_depth=3,
                             progress=self.progress.emit,
                             abort=self.isInterruptionRequested)
        except ScanAborted:
            self.aborted.emit()
            return
        self.doneOk.emit(res, time.time() - t0)


# ---------------- 控制器 ----------------
class DiskWatch(QObject):
    progress = Signal(str)
    reportReady = Signal(dict)
    workerFinished = Signal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.store = _load_store()
        self.last_report: dict | None = None
        self._worker: _ScanWorker | None = None
        self._rebuild = False

        self._timer = QTimer(self)
        self._timer.setInterval(30 * 60 * 1000)  # 每 30 分钟检查一次是否该扫
        self._timer.timeout.connect(self.auto_check)
        self._timer.start()
        QTimer.singleShot(45_000, self.auto_check)  # 启动 45 秒后建基线/补扫

    # ---- 对外 ----
    def is_scanning(self) -> bool:
        return self._worker is not None

    def start_scan(self, deep: bool | None = None, rebuild: bool = False) -> bool:
        if self._worker is not None:
            return False
        if deep is None:
            deep = bool(self.cfg.get("diskwatch_deep_scan", False))
        self._rebuild = bool(rebuild)
        worker = _ScanWorker(deep, self)
        worker.progress.connect(self.progress)
        worker.doneOk.connect(self._on_done)
        worker.aborted.connect(lambda: self.progress.emit("扫描已中止"))
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.progress.emit("开始扫描 C盘…")
        worker.start()
        return True

    def abort_scan(self) -> None:
        if self._worker is not None:
            self._worker.requestInterruption()

    def auto_check(self) -> None:
        """定时入口：没基线就补建；超过配置间隔就自动扫描。"""
        if not self.cfg.get("diskwatch_enabled", True):
            return
        if self.is_scanning():
            return
        last = self.store.get("last")
        if last is None:
            self.start_scan()
            return
        interval = float(self.cfg.get("diskwatch_interval_hours", 6)) * 3600
        if time.time() - float(last.get("time", 0)) >= interval:
            self.start_scan()

    # ---- 内部 ----
    def _on_worker_finished(self) -> None:
        self._worker = None
        self.workerFinished.emit()

    def _on_done(self, res, elapsed: float) -> None:
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            free_gb = psutil.disk_usage(drive).free / _GB
        except OSError:
            free_gb = 0.0
        new_snap = {
            "time": time.time(),
            "disk_free_gb": free_gb,
            "dirs": {p: [s, f] for p, (s, f) in res.dirs.items()},
        }
        last = self.store.get("last")
        baseline = self.store.get("baseline")
        first = baseline is None

        report = {
            "time": new_snap["time"],
            "elapsed": elapsed,
            "files_total": res.files_total,
            "size_total": res.size_total,
            "skipped": res.skipped,
            "top_last": top_growth(diff_snapshots(last, new_snap)),
            "top_baseline": top_growth(diff_snapshots(baseline, new_snap)),
            "free_gb": free_gb,
            "free_delta_gb": (last["disk_free_gb"] - free_gb) if last else None,
            "system_files": system_files_info(),
            "rebuild": self._rebuild,
            "first": first,
        }
        if first or self._rebuild:
            self.store["baseline"] = new_snap
        self.store["last"] = new_snap
        _save_store(self.store)
        self.last_report = report
        self.reportReady.emit(report)
