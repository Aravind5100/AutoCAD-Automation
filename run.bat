@echo off
REM ============================================================
REM  AutoCAD Room Annotation Tool - Launch Script
REM  Double-click this file to start the application.
REM ============================================================
title AutoCAD Room Annotator
color 0B

echo.
echo  Starting AutoCAD Room Annotation Tool...
echo.

REM ------ Check setup has been done ------
if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: Setup has not been completed yet.
    echo.
    echo  Please run setup.bat first before running this application.
    echo.
    pause
    exit /b 1
)

REM ------ Check AutoCAD is running ------
tasklist /FI "IMAGENAME eq acad.exe" 2>nul | find /I "acad.exe" >nul
if %ERRORLEVEL% NEQ 0 (
    echo  WARNING: AutoCAD does not appear to be running.
    echo.
    echo  The application requires AutoCAD to be open and running.
    echo  Please start AutoCAD now, then press any key to continue.
    echo.
    pause
)

REM ------ Launch the application ------
echo  Launching application...
echo.
.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ============================================================
    echo  The application exited with an error.
    echo.
    echo  Common fixes:
    echo    1. Make sure AutoCAD is running before starting.
    echo    2. Run setup.bat again to reinstall dependencies.
    echo    3. Check that Python is still installed correctly.
    echo  ============================================================
    echo.
    pause
)
