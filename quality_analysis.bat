@echo off
REM ============================================================
REM  Universal i18n Quality Analysis - launcher
REM  Usage:  quality_analysis.bat [--root PATH] [--report PATH]
REM                               [--lang en|it]
REM  Double-click friendly: window stays open to read results.
REM ============================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0test_universal_quality_analysis.py" %*
) else (
    python "%~dp0test_universal_quality_analysis.py" %*
)
set EXITCODE=%errorlevel%

echo.
if %EXITCODE%==0 (
    echo [OK] Analysis completed with no blocking issues.
) else (
    echo [!!] Analysis reported blocking issues ^(exit code %EXITCODE%^).
)
pause
exit /b %EXITCODE%
