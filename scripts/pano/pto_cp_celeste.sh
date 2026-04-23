#!/usr/bin/env bash
# Drop sky/cloud-region control points from a Hugin PTO via Hugin's celeste.
#
# Sky and cloud features are the main source of false CP matches between
# distant frames in outdoor panoramas — they look similar everywhere, so
# cpfind happily matches image 2's clouds against image 30's clouds. Celeste
# runs a trained SVM classifier over each image, marks pixels as sky, and
# drops any CP falling on one. Run this before pairwise adjacency filtering;
# they target the same problem from different angles and compose cleanly.
#
# Usage:
#   pto_cp_celeste.sh IN.pto OUT.pto [threshold]
#
# threshold: float in [0, 1], default 0.5.
#   Higher -> remove fewer CPs (only obvious sky).
#   Lower  -> remove more (aggressive; may clip horizon features).

set -euo pipefail

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo "usage: $0 IN.pto OUT.pto [threshold]" >&2
    exit 2
fi

IN="$1"
OUT="$2"
THRESH="${3:-0.5}"

exec celeste_standalone -i "$IN" -o "$OUT" -t "$THRESH"
