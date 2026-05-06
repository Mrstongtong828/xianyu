@echo off
:: 解决中文乱码
chcp 65001 >nul
title 闲鱼超级管家 - 启动器

echo ==========================================
echo       欢迎使用 闲鱼超级管家
echo ==========================================

:: 1. 检查 Python 
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 你的电脑没装 Python，请安装 3.11 或 3.12 版本。
    pause
    exit
)

:: 2. 强制安装核心包 (针对你的 Python 3.14 和小白同学)
echo [1/3] 正在配置核心环境...
pip install uvicorn fastapi httpx loguru pyyaml playwright --quiet

:: 3. 安装浏览器内核
echo [2/3] 正在准备浏览器组件...
playwright install chromium

:: 4. 运行
echo [3/3] 正在启动，成功后会自动弹出浏览器页面...
python Start.py

pause