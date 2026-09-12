#!/usr/bin/env bash
# Build the recon GPU image.
#
# The build context is THIS directory, not the repo root: the root is 82 GB and docker
# tars the whole context before running the first instruction. Everything the image needs
# from elsewhere in the repo is 436 KB of Python, so it gets staged into vendor/ here.
# That also means the build works identically on the VPS with both repos checked out
# wherever they happen to land.
#
#   ./build.sh                         # tag from the current commit
#   PICS_ROOT=/srv/pics ./build.sh     # pics checked out elsewhere
#   CUDA_ARCH=120 TORCH_INDEX=https://download.pytorch.org/whl/cu130 ./build.sh   # 5090
#
# Expect ~3.5 GB of downloads on a cold build: CUDA torch and the Mask2Former weights.
# Build it where the bandwidth is.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PICS_ROOT="${PICS_ROOT:-$(cd "$REPO/../../../pics/0/pics" 2>/dev/null && pwd || true)}"
CLI="src/tools/semantic_mask_inference.py"

[ -n "$PICS_ROOT" ] && [ -f "$PICS_ROOT/$CLI" ] || {
    echo "error: no pics checkout with $CLI (set PICS_ROOT)" >&2; exit 1; }

rm -rf "$HERE/vendor"
mkdir -p "$HERE/vendor/pics/src/tools" "$HERE/vendor/scripts-enrich"
cp "$PICS_ROOT/$CLI" "$HERE/vendor/pics/$CLI"
# every module reconstruct.py and worker.py import at runtime; no data files, no venvs,
# no runs/, and not the 2.6 GB mast3r_repo (the image clones its own at a pinned commit)
cp "$REPO"/scripts/enrich/*.py "$HERE/vendor/scripts-enrich/"

sha() { git -C "$1" rev-parse --short HEAD 2>/dev/null || echo "not-a-checkout"; }
echo "staged: pics $(sha "$PICS_ROOT"), scripts/enrich from hillview $(sha "$REPO")"
echo "context: $(du -sh "$HERE" | cut -f1)"

TAG="${TAG:-hillview-recon-gpu:$(sha "$REPO")}"
cd "$HERE"
exec docker build -f Dockerfile.gpu -t "$TAG" \
    ${CUDA_IMAGE:+--build-arg CUDA_IMAGE="$CUDA_IMAGE"} \
    ${TORCH_INDEX:+--build-arg TORCH_INDEX="$TORCH_INDEX"} \
    ${CUDA_ARCH:+--build-arg CUDA_ARCH="$CUDA_ARCH"} \
    ${MAST3R_REPO_URL:+--build-arg MAST3R_REPO_URL="$MAST3R_REPO_URL"} \
    "$@" .
