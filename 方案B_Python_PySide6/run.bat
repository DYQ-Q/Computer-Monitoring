@echo off
rem ============================================================
rem  用 conda 的 agent 环境启动悬浮监控（不改全局环境）
rem  如 conda 安装路径不同，请修改下面 call 那一行
rem ============================================================
call D:\software_tech\anaconda3\Scripts\activate.bat agent
cd /d %~dp0
start "" pythonw main.py
