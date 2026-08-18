#!/usr/bin/env bash
# ============================================================
#  Universal i18n Quality Analysis - install deps with NO
#  network access (Unix)
#  Installs the analyzer's two dependencies from the local
#  offline_deps/ folder. PyYAML is OPTIONAL — it is only needed
#  for YAML locale layouts, and a failure to install it is
#  reported without failing the run.
#  Usage:  ./install_offline_deps.sh
# ============================================================
set -u
cd "$(dirname "$0")"

if [ ! -d offline_deps ]; then
    echo "[!!] offline_deps/ folder not found."
    echo "     Run ./download_offline_deps.sh on an online machine first."
    exit 1
fi

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

# --no-build-isolation: when only an sdist is vendored, pip must not try to
# fetch build dependencies from an index it cannot reach.
PIP_ARGS="--no-index --no-build-isolation --find-links=offline_deps"

echo "[..] Installing langdetect (required)..."
# shellcheck disable=SC2086
"${PY}" -m pip install ${PIP_ARGS} langdetect
CODE=$?

if [ ${CODE} -ne 0 ]; then
    echo
    echo "[!!] langdetect could not be installed (exit code ${CODE})."
    echo "     Check that offline_deps/ was populated for this OS and"
    echo "     Python version. The analyzer cannot run without it."
    exit ${CODE}
fi

echo "[..] Installing PyYAML (optional, for YAML locale files)..."
# shellcheck disable=SC2086
if "${PY}" -m pip install ${PIP_ARGS} pyyaml; then
    YAML="yes"
else
    YAML="no"
fi

echo
echo "[OK] langdetect installed."
if [ "${YAML}" = "yes" ]; then
    echo "[OK] PyYAML installed - YAML locale files supported."
else
    echo "[--] PyYAML not installed - JSON and JS/TS locales still work."
    echo "     Only .yml / .yaml dictionaries will be skipped."
fi
echo "     Run:  ./quality_analysis.sh"
exit 0
