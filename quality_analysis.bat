@echo off
REM ============================================================
REM  Universal i18n Quality Analysis - launcher
REM  Usage:  quality_analysis.bat [--root PATH] [--report PATH]
REM                               [--lang en|it]
REM  Double-click friendly: window stays open to read results.
REM
REM  Settings live in .i18n-quality.json in the scanned project root, NOT
REM  in the analyzer -- which stays project-agnostic. The file is optional
REM  and writes itself the first time it is missing: a commented template
REM  with every value empty, which changes nothing until you fill
REM  something in. It declares this project's technical vocabulary, its
REM  own UI widget names, directories to skip, which noise suppressions
REM  are on, and the per-severity budgets that make findings blocking.
REM    quality_analysis.bat --vocab-help    explains it
REM    quality_analysis.bat --self-test     checks the analyzer on itself
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
