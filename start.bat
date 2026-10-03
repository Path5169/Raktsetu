@echo off
setlocal
cd /d "%~dp0"

echo.
echo  RaktSetu - Live Blood Network
echo  ============================
echo.

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found.
        echo Install Python 3.8 or newer from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist "raktsetu.db" (
    echo Creating fictional demo database...
    %PYTHON% -m raktsetu init
    if errorlevel 1 (
        echo Could not initialize the database.
        pause
        exit /b 1
    )
)

if /I "%~1"=="reset" (
    echo Resetting fictional hackathon demo data...
    %PYTHON% -m raktsetu demo-reset
    if errorlevel 1 (
        echo Could not reset the demo database.
        pause
        exit /b 1
    )
)

echo Starting RaktSetu at http://127.0.0.1:8000
echo Close this window to stop the server.
echo.
%PYTHON% -m raktsetu serve

pause
