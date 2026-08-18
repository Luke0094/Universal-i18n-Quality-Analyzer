#!/usr/bin/env bash
# ============================================================
#  Universal i18n Quality Analysis - vendor the dependencies
#  for offline use (Unix)
#  Run this ONCE on a machine WITH network access, then copy
#  the whole tests/ folder to the offline machine and run
#  ./install_offline_deps.sh there.
#  Usage:  ./download_offline_deps.sh
# ============================================================
set -u
cd "$(dirname "$0")"

PY=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1 \
            && "${cand}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        PY="${cand}"
        break
    fi
done
if [ -z "${PY}" ]; then
    echo "[!!] No working Python >= 3.10 found in PATH."
    exit 1
fi

mkdir -p offline_deps

# langdetect is pure Python, so one universal wheel covers every OS and
# every Python 3 — build it rather than downloading a platform copy.
echo "[..] langdetect (universal wheel + its six dependency)..."
"${PY}" -m pip wheel langdetect --no-deps -w offline_deps    || exit 1
"${PY}" -m pip download langdetect -d offline_deps           || exit 1

# PyYAML ships compiled wheels, so the downloaded one only fits THIS OS and
# Python version. The sdist is fetched as well so another machine can build
# it — PyYAML is optional, and the analyzer runs without it either way.
echo "[..] PyYAML (wheel for this platform + portable sdist)..."
"${PY}" -m pip download pyyaml -d offline_deps               || exit 1
"${PY}" -m pip download pyyaml --no-binary pyyaml --no-deps -d offline_deps || exit 1

echo
echo "[OK] Vendored into offline_deps/:"
ls -1 offline_deps
echo
echo "     Copy the tests/ folder to the offline machine and run"
echo "     ./install_offline_deps.sh there."
exit 0
