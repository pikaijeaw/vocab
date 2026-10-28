#!/bin/sh
# Runs both vocab syncs (HSK then TOEIC). Each commits + pushes only its own files, only if changed.
cd "$(dirname "$0")/.." || exit 1
rc=0
echo "===== HSK ====="   ; /usr/bin/python3 scripts/update_hsk.py   "$@" || rc=1
echo "===== TOEIC =====" ; /usr/bin/python3 scripts/update_toeic.py "$@" || rc=1
exit $rc
