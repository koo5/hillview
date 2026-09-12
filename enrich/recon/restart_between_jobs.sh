#!/usr/bin/env bash
# Restart the recon worker without wasting a solve.
#
# The worker is a long-lived host process, so a code change reaches it only on restart --
# and a restart mid-solve kills the solve (systemd takes the child with the unit) and,
# under the pre-2026-09-09 code, made the actor report it as an error and ACK the
# message, so it did not even requeue. This waits until the RUNNING run finishes, then
# restarts immediately; the next message will have been picked up and killed at its
# download stage, so it is requeued afterwards. Cost: a few seconds of download.
#
#   ./restart_between_jobs.sh            # wait for the current job, restart, requeue
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
API="${RECON_API:-http://127.0.0.1:8070/api/recon}"
sql() { docker exec enrich_workbench_db psql -U enrich -d enrich -At -c "$1"; }

cur="$(sql "select name from recon_runs where status='running' order by enqueued_at limit 1")"
if [ -n "$cur" ]; then
  echo "waiting for '$cur' to finish…"
  while [ "$(sql "select status from recon_runs where name='$cur'")" = "running" ]; do sleep 20; done
  echo "'$cur' -> $(sql "select status from recon_runs where name='$cur'")"
fi
# whatever the worker grabs next is about to be killed at its download stage
sleep 3
victim="$(sql "select id from recon_runs where status='running' order by enqueued_at limit 1")"
"$HERE/run_worker.sh" | tail -1
if [ -n "$victim" ]; then
  sleep 5
  st="$(sql "select status from recon_runs where id='$victim'")"
  if [ "$st" != "running" ]; then
    echo "requeueing the run the restart interrupted ($victim, was $st)"
    curl -s -X POST "$API/runs/$victim/requeue"; echo
  fi
fi
docker exec enrich_rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers 2>/dev/null | grep -E "^recon\s"
