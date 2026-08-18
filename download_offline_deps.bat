@echo off
REM ============================================================
REM  Universal i18n Quality Analysis - vendor the dependencies
REM  for offline use
REM  Run this ONCE on a machine WITH network access, then copy
REM  the whole tests\ folder to the offline machine and run
REM  install_offline_deps.bat there.
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3

if not exist offline_deps mkdir offline_deps

REM langdetect is pure Python, so one universal wheel covers every OS and
REM every Python 3 - build it rather than downloading a platform copy.
echo [..] langdetect (universal wheel + its six dependency)...
%PY% -m pip wheel langdetect --no-deps -w offline_deps
if errorlevel 1 goto failed
%PY% -m pip download langdetect -d offline_deps
if errorlevel 1 goto failed

REM Babel is pure Python too, but a big wheel: it carries the whole CLDR
REM database, which is exactly what the ICU plural check wants. Optional -
REM without it the analyzer falls back to its own smaller table.
echo [..] Babel (universal wheel, optional)...
%PY% -m pip download babel -d offline_deps
if errorlevel 1 goto failed

REM PyYAML ships compiled wheels, so the downloaded one only fits THIS OS
REM and Python version. The sdist is fetched as well so another machine can
REM build it - PyYAML is optional, and the analyzer runs without it anyway.
echo [..] PyYAML (wheel for this platform + portable sdist)...
%PY% -m pip download pyyaml -d offline_deps
if errorlevel 1 goto failed
%PY% -m pip download pyyaml --no-binary pyyaml --no-deps -d offline_deps
if errorlevel 1 goto failed

REM tree-sitter gives the analyzer a real parse tree for 300+ languages
REM instead of a regex. Both wheels are COMPILED, so what lands here
REM fits this OS and Python only, and there is no practical sdist path:
REM the language pack would have to build every grammar from source.
REM When the wheel does not fit, the analyzer falls back to the regex
REM extractor, which is the whole reason that fallback exists.
echo [..] tree-sitter (parse trees for non-Python sources, optional)...
%PY% -m pip download tree-sitter tree-sitter-language-pack -d offline_deps
if errorlevel 1 goto failed

echo.
echo [OK] Vendored into offline_deps\:
dir /b offline_deps
echo.
echo      Copy the tests\ folder to the offline machine and run
echo      install_offline_deps.bat there.
pause
exit /b 0

:failed
echo.
echo [!!] Download failed - check the network connection and try again.
pause
exit /b 1
