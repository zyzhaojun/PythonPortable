@echo off
setlocal
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"

if not exist "runtimes\python312\python.exe" (
    echo Missing runtimes\python312\python.exe
    pause
    exit /b 1
)

if not exist "runtimes\python37\python.exe" (
    echo Missing runtimes\python37\python.exe
    pause
    exit /b 1
)

if not exist "teaching_shell.py" (
    echo Missing teaching_shell.py
    pause
    exit /b 1
)

echo Starting portable Python teaching shell with Python 3.7 launcher...
echo The browser will open automatically.
echo Keep this window open while using it.
echo.

"%~dp0runtimes\python37\python.exe" "%~dp0teaching_shell.py"
echo.
echo Portable Python teaching shell has stopped.
pause
endlocal
