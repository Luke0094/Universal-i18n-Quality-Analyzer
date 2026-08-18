@echo off
REM ============================================================
REM  Universal i18n Quality Analysis - install deps with NO
REM  network access
REM  Installs the analyzer's two dependencies from the local
REM  offline_deps\ folder. PyYAML, Babel and tree-sitter are OPTIONAL - it is only needed
REM  for YAML locale layouts, and a failure to install it is
REM  reported without failing the run.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist offline_deps (
    echo [!!] offline_deps\ folder not found.
    echo      Run download_offline_deps.bat on an online machine first.
    pause
    exit /b 1
)

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3

REM --no-build-isolation: when only an sdist is vendored, pip must not try
REM to fetch build dependencies from an index it cannot reach.
set PIPARGS=--no-index --no-build-isolation --find-links=offline_deps

echo [..] Installing langdetect (required)...
%PY% -m pip install %PIPARGS% langdetect
set EXITCODE=%errorlevel%

if not %EXITCODE%==0 (
    echo.
    echo [!!] langdetect could not be installed ^(exit code %EXITCODE%^).
    echo      Check that offline_deps\ was populated for this OS and
    echo      Python version. The analyzer cannot run without it.
    pause
    exit /b %EXITCODE%
)

echo [..] Installing PyYAML (optional, for YAML locale files)...
%PY% -m pip install %PIPARGS% pyyaml
set YAMLCODE=%errorlevel%

echo [..] Installing Babel (optional, for authoritative CLDR plural rules)...
%PY% -m pip install %PIPARGS% babel
set BABELCODE=%errorlevel%

echo [..] Installing tree-sitter (optional, parse trees for non-Python sources)...
%PY% -m pip install %PIPARGS% tree-sitter tree-sitter-language-pack
set TSCODE=%errorlevel%

echo.
echo [OK] langdetect installed.
if %YAMLCODE%==0 (
    echo [OK] PyYAML installed - YAML locale files supported.
) else (
    echo [--] PyYAML not installed - JSON and JS/TS locales still work.
    echo      Only .yml / .yaml dictionaries will be skipped.
)
if %BABELCODE%==0 (
    echo [OK] Babel installed - ICU plural rules checked against real CLDR.
) else (
    echo [--] Babel not installed - ICU plural coverage still checked,
    echo      from a smaller built-in table, and never blocking.
)
if %TSCODE%==0 (
    echo [OK] tree-sitter installed - JS/TS/Vue/PHP/Kotlin/Go/... read from a parse tree.
) else (
    echo [--] tree-sitter not installed - non-Python sources fall back
    echo      to the regex extractor. Keys are still found; a t() written
    echo      inside a string or a mid-line comment may count as one.
)
echo      Run:  quality_analysis.bat
pause
exit /b 0
