"""C盘增长侦探自测：
1) 扫描器聚合 / 深度上限 / 差值 / 排行去重（纯逻辑）
2) DiskWatch 线程 + ReportWindow 离屏冒烟（monkeypatch 到小目录，不扫真实磁盘）

用法（agent env，在 方案B_Python_PySide6 目录下）：
    python tools/test_diskwatch.py
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MB = 1024 * 1024


def part1() -> bool:
    from app import diskwatch as dw
    from app.scanner import scan_roots

    base_root = os.path.join(ROOT, "tools", "_dwtest1")
    shutil.rmtree(base_root, ignore_errors=True)
    os.makedirs(base_root, exist_ok=True)
    base = os.path.join(base_root, "root")
    os.makedirs(os.path.join(base, "a", "sub"))
    os.makedirs(os.path.join(base, "b"))

    def mk(rel: str, size: int) -> None:
        with open(os.path.join(base, rel), "wb") as f:
            f.write(b"0" * size)

    mk(os.path.join("a", "big1.bin"), 3 * MB)
    mk(os.path.join("a", "sub", "big2.bin"), 2 * MB)
    mk(os.path.join("b", "old.bin"), 1 * MB)
    mk("deep.bin", 1 * MB)

    ok = True
    s1 = scan_roots([(base, "test")], max_depth=3)
    got = s1.dirs[base][0]
    print(f"[1] root aggregate: got={got} expect={7 * MB}")
    ok = ok and got == 7 * MB and s1.files_total == 4

    # 深度上限：z(深度3)记录，w(深度4)不记录，但 z 的聚合包含 w 的内容
    os.makedirs(os.path.join(base, "x", "y", "z", "w"))
    mk(os.path.join("x", "y", "z", "w", "f.bin"), 10 * MB)
    mk(os.path.join("x", "y", "z", "zz.bin"), 5 * MB)
    s2 = scan_roots([(base, "test")], max_depth=3)
    z_path = os.path.join(base, "x", "y", "z")
    w_path = os.path.join(z_path, "w")
    has_z, has_w = z_path in s2.dirs, w_path in s2.dirs
    z_size = s2.dirs.get(z_path, (0, 0))[0]
    print(f"[1] depth cap: z recorded={has_z}(True) w recorded={has_w}(False) "
          f"z aggregate={z_size}(expect {15 * MB})")
    ok = ok and has_z and not has_w and z_size == 15 * MB

    # 差值 + 排行：b 新增 4MB
    mk(os.path.join("b", "new.bin"), 4 * MB)
    s3 = scan_roots([(base, "test")], max_depth=3)
    deltas = dw.diff_snapshots({"dirs": s2.dirs}, {"dirs": s3.dirs})
    top = dw.top_growth(deltas)
    b_path = os.path.join(base, "b")
    print(f"[1] deltas[b]={deltas.get(b_path)} expect={4 * MB}; "
          f"top={[(os.path.basename(p), d) for p, d in top]}")
    ok = ok and deltas.get(b_path) == 4 * MB
    ok = ok and any(p == base and d == 4 * MB for p, d in top)

    shutil.rmtree(base_root, ignore_errors=True)
    print("PART1", "PASS" if ok else "FAIL")
    return ok


def part2() -> bool:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app import config as cfgmod
    from app import diskwatch as dw
    from app.diskwatch import DiskWatch
    from app.report_window import ReportWindow

    tmp = os.path.join(ROOT, "tools", "_dwtest2")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    dw.SNAP_FILE = os.path.join(tmp, "snap.json")
    dw.DATA_DIR = tmp
    fake_c = os.path.join(tmp, "fake_c")
    os.makedirs(os.path.join(fake_c, "Temp"))
    with open(os.path.join(fake_c, "Temp", "x.bin"), "wb") as f:
        f.write(b"0" * (2 * MB))
    dw.build_roots = lambda deep=False: [(fake_c, "测试根")]  # 不扫真实磁盘

    app = QApplication([])
    cfg = cfgmod.load()
    watch = DiskWatch(cfg)
    win = ReportWindow(watch, cfg)
    win.show()

    state = {"phase": 0, "ok": False}

    def on_report(rep: dict) -> None:
        if state["phase"] == 0:
            state["phase"] = 1
            print(f"[2] first scan: files={rep['files_total']} first={rep['first']}")
            with open(os.path.join(fake_c, "Temp", "y.bin"), "wb") as f:
                f.write(b"0" * (3 * MB))
            QTimer.singleShot(200, lambda: watch.start_scan())
        else:
            hit = any(os.path.basename(p) == "Temp" and d == 3 * MB
                      for p, d in rep["top_last"])
            state["ok"] = hit and win.table.rowCount() >= 1
            print(f"[2] second scan: top_last={[(os.path.basename(p), d) for p, d in rep['top_last']]} "
                  f"table_rows={win.table.rowCount()} hit={hit}")

    watch.reportReady.connect(on_report)
    watch.start_scan()
    QTimer.singleShot(20000, app.quit)  # 超时保护
    app.exec()

    shutil.rmtree(tmp, ignore_errors=True)
    print("PART2", "PASS" if state["ok"] else "FAIL")
    return state["ok"]


if __name__ == "__main__":
    ok1 = part1()
    ok2 = part2()
    ok = ok1 and ok2
    print("DISKWATCH TEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
