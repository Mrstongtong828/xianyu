@echo off
chcp 65001 >/dev/null
set PYTHONIOENCODING=utf-8
set NO_COLOR=1
title 闲鱼超级管家 - 运行中
cd /d %~dp0

echo ==========================================
echo       欢迎使用 闲鱼超级管家
echo ==========================================

python --version >/dev/null 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit
)

echo [1/3] 检查并安装依赖...
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [2/3] 检查浏览器驱动...
playwright install chromium >/dev/null 2>&1

echo [3/3] 启动程序，浏览器将自动打开...
python Start.py

pause
