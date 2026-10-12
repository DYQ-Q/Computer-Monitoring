"""C盘目录体积扫描器：递归统计每个目录的聚合大小与文件数。

设计要点：
- 不跟随 junction / 符号链接（FILE_ATTRIBUTE_REPARSE_POINT），防环、防重复计数；
- 无权限目录记入 skipped，不让整个扫描失败 —— 普通用户权限即可运行，
  管理员只是能多覆盖一些系统目录；
- 全量递归聚合，但只"存储"每棵扫描根下相对深度 <= max_depth 的目录，
  控制快照文件体积（WinDirStat 式的完整树状可视化留作后续）。
"""
from __future__ import annotations

import os

REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
SKIP_NAMES = {"System Volume Information"}


class ScanAborted(Exception):
    """外部要求中止扫描（如用户退出程序）。"""


class ScanResult:
    __slots__ = ("dirs", "skipped", "files_total", "size_total")

    def __init__(self) -> None:
        self.dirs: dict[str, tuple[int, int]] = {}   # path -> (聚合字节, 文件数)
        self.skipped: list[str] = []                 # 无权限/无法读取的目录
        self.files_total = 0
        self.size_total = 0


def build_roots(deep: bool = False) -> list[tuple[str, str]]:
    """扫描根清单：日常膨胀的惯犯目录 + 用户目录。

    deep=True 时加入 Windows / Program Files（慢，且包含上面的系统子目录，
    因此去掉重复的子根）。
    """
    home = os.path.expanduser("~")
    roots = [
        (home, "用户目录"),
        (r"C:\Windows\Temp", "系统临时文件"),
        (r"C:\Windows\SoftwareDistribution\Download", "Windows更新缓存"),
        (r"C:\ProgramData", "ProgramData"),
        (r"C:\$Recycle.Bin", "回收站"),
    ]
    if deep:
        roots = [r for r in roots if not r[0].lower().startswith("c:\\windows\\")]
        roots += [
            (r"C:\Windows", "Windows系统目录(较慢)"),
            (r"C:\Program Files", "Program Files"),
            (r"C:\Program Files (x86)", "Program Files (x86)"),
        ]
    return [(p, label) for p, label in roots if os.path.isdir(p)]


def system_files_info() -> list[tuple[str, int]]:
    """C盘根目录的系统大文件（页面/休眠文件），只读元数据，读不到就忽略。"""
    out: list[tuple[str, int]] = []
    for name in ("hiberfil.sys", "pagefile.sys", "swapfile.sys"):
        try:
            out.append((name, os.stat(os.path.join("C:\\", name)).st_size))
        except OSError:
            pass
    return out


def scan_roots(roots: list[tuple[str, str]], max_depth: int = 3,
               progress=None, abort=None) -> ScanResult:
    """扫描多棵目录树；abort() 返回 True 时抛出 ScanAborted 快速退出。"""
    res = ScanResult()
    for path, label in roots:
        if abort and abort():
            raise ScanAborted()
        if progress:
            progress(f"扫描 {label}: {path}")
        try:
            size, _files = _walk(path, res, max_depth, 0, abort)
        except ScanAborted:
            raise
        except OSError:
            res.skipped.append(path)
            continue
        res.size_total += size
    return res


def _walk(dirpath: str, res: ScanResult, max_depth: int, depth: int,
          abort) -> tuple[int, int]:
    if abort and abort():
        raise ScanAborted()
    try:
        it = os.scandir(dirpath)
    except OSError:
        res.skipped.append(dirpath)
        return 0, 0

    size = 0
    files = 0
    with it:
        for entry in it:
            try:
                if entry.is_dir(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    if st.st_file_attributes & REPARSE_POINT:
                        continue  # junction / 符号链接：不跟随
                    if entry.name in SKIP_NAMES:
                        continue
                    s, f = _walk(entry.path, res, max_depth, depth + 1, abort)
                    size += s
                    files += f
                elif entry.is_file(follow_symlinks=False):
                    size += entry.stat(follow_symlinks=False).st_size
                    files += 1
                    res.files_total += 1
            except OSError:
                continue  # 单个条目读不了就跳过

    if depth <= max_depth:
        res.dirs[dirpath] = (size, files)
    return size, files
