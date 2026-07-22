#!/usr/bin/env bash
# ============================================================
#  Universal i18n Quality Analysis - launcher (Unix)
#  Usage:  ./quality_analysis.sh [--root PATH] [--report PATH]
#                                [--lang en|it]
#  Exit code: 0 = clean, 1 = blocking issues (CI-friendly).
# ============================================================
set -u
cd "$(dirname "$0")"

PY=""
for cand in python3 python; do
    if command -v "${cand}" >/dev/null 2>&1             && "${cand}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        PY="${cand}"
        break
    fi
done
if [ -z "${PY}" ]; then
    echo "[!!] No working Python >= 3.10 found in PATH."
    exit 1
fi

"${PY}" ./test_universal_quality_analysis.py "$@"
CODE=$?

echo
if [ ${CODE} -eq 0 ]; then
    echo "[OK] Analysis completed with no blocking issues."
else
    echo "[!!] Analysis reported blocking issues (exit code ${CODE})."
fi
exit ${CODE}
