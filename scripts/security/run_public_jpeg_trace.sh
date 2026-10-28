#!/usr/bin/env bash
# Usage: bash scripts/security/run_public_jpeg_trace.sh IMAGE_ID OUTPUT_DIR
# IMAGE_ID must be the immutable worker image to examine. No service changes.
set -euo pipefail
image_id=${1:?Supply the immutable worker image ID}
output_dir=${2:?Supply an output directory}
repo_dir=$(git rev-parse --show-toplevel)
mkdir -p "$output_dir"
printf '%s\n' "$image_id" > "$output_dir/image-id.txt"
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1g --cpus 1 --pids-limit 64 \
  --user 1001:1001 --tmpfs /tmp:rw,size=128m \
  --tmpfs /app/uploads:rw,size=64m,uid=1001,gid=1001 \
  -v /dev/null:/app/worker/.env:ro \
  -v "$repo_dir/backend:/review/backend:ro" \
  -v "$repo_dir/scripts/security:/review/probes:ro" \
  -e PYTHONPATH=/review/backend/worker:/review/backend:/review/backend/common \
  -e PERL5LIB=/review/probes -e PERL5OPT=-MHillviewTrace \
  --entrypoint python "$image_id" /review/probes/public_jpeg_trace.py \
  > "$output_dir/trace.json" 2> "$output_dir/trace.stderr"
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --cpus 1 --pids-limit 32 \
  --user 1001:1001 --tmpfs /tmp:rw,size=16m \
  -v "$repo_dir/scripts/security:/review/probes:ro" \
  -e PERL5LIB=/review/probes -e PERL5OPT=-MHillviewTrace \
  -e HILLVIEW_TRACE_FILE=/tmp/control.trace --entrypoint sh "$image_id" \
  -c 'perl /review/probes/exiftool_gm_control.pl && cat /tmp/control.trace' \
  > "$output_dir/gm-control.txt" 2> "$output_dir/gm-control.stderr"
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --cpus 1 --pids-limit 32 \
  --user 1001:1001 --tmpfs /tmp:rw,size=16m \
  -v "$repo_dir/scripts/security:/review/probes:ro" --entrypoint python \
  "$image_id" /review/probes/exiftool_patch_control.py \
  > "$output_dir/gm-patch-control.json" 2> "$output_dir/gm-patch-control.stderr"
