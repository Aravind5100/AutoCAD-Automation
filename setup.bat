@echo off
REM ============================================================
REM  AutoCAD Room Annotation Tool - Setup Script
REM  Run this ONCE before using the application.
REM ============================================================
title AutoCAD Room Annotator - Setup
color 0A

echo.
echo  ============================================================
echo    AutoCAD Room Annotation Tool - First-Time Setup
echo  ============================================================
echo.

REM ------ Check Python is installed ------
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Python is not installed or not in your PATH.
    echo.
    echo  Please install Python 3.10 or later from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, check the box that says:
    echo    "Add Python to PATH"
    echo.
    echo  After installing Python, close this window and run setup.bat again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  Found Python %PYVER%

REM ------ Check Python version is 3.10+ ------
python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Python 3.10 or later is required.
    echo  Your version: %PYVER%
    echo.
    echo  Please upgrade Python from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM ------ Create virtual environment ------
echo.
echo [2/4] Creating virtual environment...
if exist ".venv" (
    echo  Virtual environment already exists. Skipping creation.
) else (
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo  Try running: python -m venv .venv
        echo.
        pause
        exit /b 1
    )
    echo  Virtual environment created successfully.
)

REM ------ Install dependencies ------
echo.
echo [3/4] Installing dependencies (this may take 1-2 minutes)...
.venv\Scripts\pip.exe install --upgrade pip >nul 2>&1
.venv\Scripts\pip.exe install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Failed to install dependencies.
    echo  Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

REM ------ Verify installation ------
echo.
echo [4/4] Verifying installation...
.venv\Scripts\python.exe -c "import pandas; import ezdxf; import win32com.client; import PySide6.QtWidgets; print('  All dependencies verified successfully.')"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  WARNING: Some dependencies may not have installed correctly.
    echo  The application may still work. Try running it with run.bat
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Setup Complete!
echo  ============================================================
echo.
echo  To start the application, double-click:  run.bat
echo.
echo  Prerequisites before running:
echo    - AutoCAD must be installed and running on this machine.
echo    - Have your DWG file and spreadsheet (CSV or Excel) ready.
echo.
pause
