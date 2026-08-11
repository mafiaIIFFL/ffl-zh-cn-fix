@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo        FFL中文翻译及修复补丁 - 安装
echo ==============================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 patcher.py install
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python patcher.py install
    ) else (
        echo [错误] 未检测到 Python 3。
        echo 请安装 Python 3.10 或更高版本，或从 GitHub Releases 下载独立 EXE 版。
        pause
        exit /b 1
    )
)

echo.
pause
