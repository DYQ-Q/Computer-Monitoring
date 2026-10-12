"""配置读写：全部配置保存在项目根目录 config.json，程序可随时热改并持久化。"""
from __future__ import annotations

import json
import os
import tempfile

APP_NAME = "SysWatcher"
APP_TITLE = "电脑状态悬浮监控"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_ROOT, "config.json")

DEFAULTS = {
    "interval_ms": 1000,                 # 采样间隔（毫秒）
    "history_len": 120,                  # 曲线保留点数，120 点 ≈ 2 分钟
    # ---- 告警 ----
    "memory_alert_threshold": 85.0,      # 内存占用告警阈值（%）
    "memory_alert_hold_seconds": 10,     # 超过阈值持续多久才告警（防抖）
    "memory_alert_cooldown_seconds": 300,# 两次内存告警的最小间隔
    "cpu_alert_threshold": 0,            # 0 = 关闭 CPU 占用告警
    "disk_alert_min_gb": 10.0,           # C盘剩余空间低于该值告警（GB）
    "disk_alert_cooldown_seconds": 3600,
    # ---- 悬浮窗 ----
    "overlay_x": -1,                     # -1 = 自动停靠屏幕右上角
    "overlay_y": 40,
    "compact": False,                    # True = 迷你条形态
    "click_through": False,              # 鼠标穿透（打游戏时开着不挡操作）
    "show_overlay": True,
    "bg_opacity": 0.8,                   # 悬浮窗背景不透明度 0~1（只影响背景，文字/占用条不变）
    # ---- C盘增长侦探 ----
    "diskwatch_enabled": True,           # 关闭后不再自动扫描（手动扫描仍可用）
    "diskwatch_interval_hours": 6,       # 自动扫描间隔（小时）
    "diskwatch_deep_scan": False,        # 深度扫描：额外包含 Windows / Program Files（较慢）
}


def load() -> dict:
    """读取配置；损坏或缺失时回退默认值，绝不抛异常影响启动。"""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user, dict):
            for key in DEFAULTS:
                if key in user:
                    cfg[key] = user[key]
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[config] 读取失败，使用默认配置: {exc}")
    return cfg


def save(cfg: dict) -> None:
    """把 DEFAULTS 中的键写回 config.json（先写临时文件再替换，防止写坏）。"""
    data = {key: cfg.get(key, default) for key, default in DEFAULTS.items()}
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CONFIG_FILE), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except Exception as exc:  # noqa: BLE001
        print(f"[config] 保存失败: {exc}")
