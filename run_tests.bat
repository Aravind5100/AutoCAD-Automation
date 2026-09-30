@echo off
REM ============================================================
REM  AutoCAD Room Annotation Tool - Automated Tests
REM  run_tests.bat        offline tests (no AutoCAD needed)
REM  run_tests.bat acad   also run the real-AutoCAD tests
REM ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: Run setup.bat first.
    exit /b 1
)

if /I "%~1"=="acad" (
    set RUN_ACAD_TESTS=1
    echo  Including real-AutoCAD tests - AutoCAD will be used.
)

.venv\Scripts\python.exe -W ignore::DeprecationWarning -m unittest discover -s tests -t . -v
set RESULT=%ERRORLEVEL%
set RUN_ACAD_TESTS=
exit /b %RESULT%
