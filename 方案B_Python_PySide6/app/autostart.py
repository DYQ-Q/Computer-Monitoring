"""开机自启：写当前用户（HKCU）的注册表 Run 键。

不需要管理员权限、不弹 UAC、不影响系统其他设置；
打包成 exe 后也能正确指向 exe 自身。
"""
from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SysWatcher"

_IS_WIN = sys.platform == "win32"
if _IS_WIN:
    import winreg


def _command() -> str:
    """自启时执行的命令行：打包后指向 exe；脚本运行时用 pythonw 静默启动。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "main.py")
    )
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{main_py}"'


def is_enabled() -> bool:
    if not _IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    if not _IS_WIN:
        return False
    try:
        if on:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        return True
    except OSError as exc:
        print(f"[autostart] 设置失败: {exc}")
        return False
