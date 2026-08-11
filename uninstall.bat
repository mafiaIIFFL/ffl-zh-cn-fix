@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo        FFL中文翻译及修复补丁 - 恢复备份
echo ==============================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 patcher.py uninstall
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python patcher.py uninstall
    ) else (
        echo [错误] 未检测到 Python 3。
        pause
        exit /b 1
    )
)

echo.
pause
