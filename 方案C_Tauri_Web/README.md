# 方案C：Tauri 2（Rust + Web 前端）—— 预留

此文件夹保留给"界面最好看、体积最小"的路线（安装包约 10-20MB）。

## 技术要点

- **框架**：Tauri 2，前端任意（原生 HTML/JS 或 Vue/React），后端 Rust。
- **窗口**：`transparent: true` + `alwaysOnTop: true` + `decorations: false`；
  点击穿透用 `set_ignore_cursor_events(true)`。
- **数据源**：
  - CPU / 内存 / 磁盘：`sysinfo` crate
  - GPU：NVML（`nvml-wrapper`）/ ADLX
  - 温度：`sysinfo` 的温度接口在 Windows 上覆盖有限，仍建议走
    LibreHardwareMonitor（命令行/子进程或 WMI 桥）
- **注意事项**：需要 Rust 工具链；温度与 NTFS USN Journal 需要写不少的
  Rust FFI/原生代码，开发成本高于方案A/B。

## 何时启用

当产品形态在方案B中验证完毕、且"颜值/体积"优先级提高时，用此路线重写 UI 层，
后端逻辑可参考方案B的 Python 实现逐模块移植。
