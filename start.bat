@echo off
title VDownloader — Local Video Downloader
color 0A

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   🎬  VDownloader — Universal Video Downloader   ║
echo  ╚══════════════════════════════════════════════════╝
echo.

REM ── Find a working Python with pip ────────────────────────
set PYTHON_CMD=

REM Try 'python' from PATH first
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python -c "import pip" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=python
        goto :found_python
    )
)

REM Try 'python3' from PATH
python3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python3
    goto :found_python
)

REM Try known Windows Store / alternate Python location
for %%P in (
    "C:\Users\New\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    "C:\Users\New\AppData\Local\Programs\Python\Python314\python.exe"
    "C:\Users\New\AppData\Local\Programs\Python\Python313\python.exe"
    "C:\Users\New\AppData\Local\Programs\Python\Python312\python.exe"
    "C:\Users\New\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python312\python.exe"
) do (
    if exist %%P (
        set PYTHON_CMD=%%P
        goto :found_python
    )
)

echo  [ERROR] Could not find Python. Install from https://python.org
pause
exit /b 1

:found_python
echo  [OK] Using Python: %PYTHON_CMD%
echo.

echo  [1/3] Installing / upgrading dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt --quiet --upgrade
if %ERRORLEVEL% NEQ 0 (
    echo  [WARN] pip install encountered issues. Trying to continue...
)

echo  [2/3] Updating yt-dlp to latest version...
%PYTHON_CMD% -m pip install --upgrade yt-dlp --quiet

echo  [3/3] Launching VDownloader...
echo.
echo  ► Browser will open at:  http://localhost:7878
echo  ► Press Ctrl+C to stop.
echo.

%PYTHON_CMD% app.py

pause
