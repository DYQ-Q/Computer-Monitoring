# 方案A：C# / WPF（.NET 8）—— 预留

此文件夹保留给"正式版"技术栈。当前先用方案B（Python）验证产品形态，后续若需要
更轻量（约 40-70MB 内存）和更强的底层能力，可按下面的设计要点重写。

## 技术要点

- **框架**：.NET 8 + WPF，`WindowStyle=None` + `AllowsTransparency` + `Topmost`
  做悬浮窗；`WS_EX_TOOLWINDOW` 不占 Alt+Tab；`WS_EX_TRANSPARENT` 做点击穿透。
- **数据源**：
  - CPU / 内存：`PerformanceCounter` 或 `NtQuerySystemInformation`
  - GPU：NVIDIA→NVML（`NvAPIWrapper`），AMD→ADLX
  - 温度：`LibreHardwareMonitorLib`（开源，需管理员权限）
  - 磁盘：`DriveInfo`
- **C盘检测（v0.2+）**：
  - 快照 diff：`Directory.EnumerateFileSystemEntries` 低优先级全扫 + 前后对比
  - 进阶：P/Invoke 读 NTFS **USN Journal**，不重扫即可实时感知文件变化
  - 盯防清单：Temp、SoftwareDistribution\Download、浏览器缓存、微信/QQ 文件、
    Windows\Installer、WinSxS、hiberfil.sys/pagefile、回收站、开发缓存
- **开机自启**：注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
  （用户级免管理员）或任务计划程序（可延迟启动）。
- **打包**：dotnet publish 自包含单文件 exe，或 framework-dependent（需 .NET 运行时）。

## 与方案B的功能对应

方案B中已验证的交互（悬浮窗形态、告警阈值、托盘行为、配置项）可直接平移过来。
