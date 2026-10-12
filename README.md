# 电脑系统监测 —— 项目总览

目标：做一个**桌面常驻、轻量**的电脑状态监控工具，解决两个痛点：

1. **实时状态悬浮显示**（CPU / 内存 / C盘），不用打开任务管理器也能随时掌握，
   内存快满时主动弹窗告警，避免"玩着玩着爆内存闪退"。
2. **C盘增长侦探**（规划中）：后台挂机，找出 C 盘空间到底被谁吃掉的。

## 目录结构

| 文件夹 | 技术方案 | 状态 |
|---|---|---|
| `方案B_Python_PySide6` | Python 3.11 + PySide6 + psutil | **✅ 开发中（MVP：悬浮监控 + 内存告警）** |
| `方案A_CSharp_WPF` | C# / WPF (.NET 8) | 预留（设计要点见其 README） |
| `方案C_Tauri_Web` | Tauri 2 (Rust + Web 前端) | 预留（设计要点见其 README） |

## 方案对比（为什么先做 B）

| | A：C#/WPF | **B：Python/PySide6** | C：Tauri |
|---|---|---|---|
| 内存占用 | ~40-70MB | ~120-200MB | ~50-80MB |
| 开发速度 | 中 | **最快** | 中偏慢 |
| 温度/底层能力 | 最好 | 一般（需桥接） | 需 Rust 生态 |
| 定位 | 正式版候选 | **原型 / 可日常使用** | UI 最好看 |

先用 B 快速做出能日常使用的版本验证交互；后续如追求更轻量，可按 A 的设计重写。

## 环境约束（重要）

- Python 相关的 **pip / conda 安装只允许在 conda 的 `agent` 环境中进行**
  （`conda activate agent`），**不得动全局环境和其他虚拟环境**。
- agent 环境路径：`D:\software_tech\anaconda3\envs\agent`（Python 3.11.17）。

## 快速开始（方案B）

```bat
cd 方案B_Python_PySide6
:: 首次：仅在 agent 环境安装依赖
conda activate agent
pip install -r requirements.txt
:: 运行
python main.py
```

或者直接双击 `方案B_Python_PySide6\run.bat`（内部自动激活 agent 环境）。

## 路线图

- [x] 方案对比与选型
- [x] **MVP**：悬浮监控窗（CPU/内存/C盘 + 曲线）+ 内存阈值告警 + 托盘 + 开机自启
- [x] **v0.2**：C盘增长侦探（快照差值、增长 Top 榜、报告窗口、自动扫描 + 下降告警）
- [ ] v0.3：GPU/温度（需管理员，暂缓）+ NTFS USN Journal 秒级实时追踪（需管理员）+ WinDirStat 式可视化
