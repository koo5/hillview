#!/usr/bin/env python3
"""Live fleet status for the hillview-worker Fly app.

Enumerates machines via `fly status --json`, then polls each machine's own
`/status` endpoint (the rich worker_status snapshot: pending queue, slots,
processing, stall, RAM, active phases) and renders it as a refreshing table.

Individual machines are targeted through Fly's public edge using the
`fly-force-instance-id` header, so no WireGuard / `fly proxy` / ssh is needed --
only that `fly` is authenticated (for the machine list) and the app exposes a
public HTTP service (hillview-worker does: 8056 -> 80/443).

Usage:
    ./fly_worker_status.py                 # live loop, refreshes every 5s
    ./fly_worker_status.py --once          # single snapshot, then exit
    ./fly_worker_status.py --interval 2    # faster refresh
    ./fly_worker_status.py --app other-app

Only machines in the `started` state are polled -- suspended/stopped machines
are listed but not hit, so this tool never autostarts a sleeping machine.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

DEFAULT_APP = "hillview-worker"

# ANSI helpers (disabled when stdout is not a tty or --no-color) -------------
_COLOR = sys.stdout.isatty()


def c(text, code):
	if not _COLOR:
		return str(text)
	return f"\x1b[{code}m{text}\x1b[0m"


def green(t):  return c(t, "32")
def red(t):    return c(t, "31")
def yellow(t): return c(t, "33")
def cyan(t):   return c(t, "36")
def dim(t):    return c(t, "2")
def bold(t):   return c(t, "1")


def read_app_from_fly_toml():
	"""Best-effort: read `app = '...'` from backend/fly.toml next to this script."""
	toml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fly.toml")
	try:
		with open(toml_path, "r") as f:
			for line in f:
				m = re.match(r"\s*app\s*=\s*['\"]([^'\"]+)['\"]", line)
				if m:
					return m.group(1)
	except OSError:
		pass
	return None


def fly_status(app):
	"""Run `fly status --json`; return the parsed dict or raise RuntimeError."""
	try:
		proc = subprocess.run(
			["fly", "status", "--json", "-a", app],
			capture_output=True, text=True, timeout=45,
		)
	except FileNotFoundError:
		raise RuntimeError("`fly` CLI not found on PATH")
	except subprocess.TimeoutExpired:
		raise RuntimeError("`fly status` timed out")
	if proc.returncode != 0:
		raise RuntimeError((proc.stderr or proc.stdout or "fly status failed").strip())
	return json.loads(proc.stdout)


def check_health(machine):
	"""Summarise the machine's Fly health checks -> 'ok' | 'warn' | 'FAIL' | '-'."""
	checks = machine.get("checks") or []
	if not checks:
		return "-"
	statuses = {ck.get("status") for ck in checks}
	if "critical" in statuses:
		return "FAIL"
	if "warning" in statuses:
		return "warn"
	if statuses == {"passing"}:
		return "ok"
	return ",".join(sorted(s for s in statuses if s))


def poll_status(base_url, endpoint, machine_id, timeout):
	"""GET {base_url}{endpoint} pinned to machine_id. Returns (dict|None, err|None)."""
	req = urllib.request.Request(
		base_url + endpoint,
		headers={"fly-force-instance-id": machine_id, "accept": "application/json"},
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			return json.loads(resp.read().decode()), None
	except urllib.error.HTTPError as e:
		return None, f"HTTP {e.code}"
	except urllib.error.URLError as e:
		return None, str(getattr(e, "reason", e))
	except (TimeoutError, json.JSONDecodeError, OSError) as e:
		return None, type(e).__name__


def norm_phase(phase):
	"""Collapse the numeric variants of wait_stagger so they aggregate."""
	return re.sub(r"(wait_stagger)_\d+s", r"\1", phase or "")


def phase_summary(active_phases, width):
	"""Compact 'name xN name xN ...' of the machine's active phases."""
	counts = {}
	for p in active_phases or []:
		name = norm_phase(p.get("phase"))
		counts[name] = counts.get(name, 0) + 1
	if not counts:
		return dim("-")
	parts = [f"{name}×{n}" for name, n in sorted(counts.items(), key=lambda kv: -kv[1])]
	s = " ".join(parts)
	if len(s) > width:
		s = s[: width - 1] + "…"
	return s


HEADER = (
	f"{'MACHINE':<14} {'REG':<3} {'STATE':<7} {'CHK':<4} "
	f"{'PEND':>7} {'SLOT':>5} {'PROC':>4} {'STALL':>5} {'QUEUE':>5} "
	f"{'RAM':>6} {'STGR':>5}  PHASES"
)


def render(app, base_url, machines, results, list_age):
	term_w = os.get_terminal_size().columns if sys.stdout.isatty() else 120
	lines = []
	now = time.strftime("%H:%M:%S")
	up = sum(1 for m in machines if m.get("state") == "started")
	lines.append(
		f"{bold(app)}  {dim(base_url)}   "
		f"{len(machines)} machines ({up} started)   "
		f"{cyan(now)}  {dim('(list %ds old, ctrl-c to quit)' % int(list_age))}"
	)
	lines.append(dim(HEADER))

	fixed_w = 14 + 1 + 3 + 1 + 7 + 1 + 4 + 1 + 7 + 1 + 5 + 1 + 4 + 1 + 5 + 1 + 5 + 1 + 6 + 1 + 5 + 2
	phase_w = max(10, term_w - fixed_w)

	# Aggregates over polled (started + reachable) machines.
	tot = {"pend": 0, "max": 0, "slots": 0, "conc": 0, "proc": 0, "stall": 0, "queue": 0}
	rams = []
	fleet_phases = {}
	reachable = 0

	for m in sorted(machines, key=lambda x: (x.get("region", ""), x.get("id", ""))):
		mid = m.get("id", "?")
		reg = m.get("region", "?")
		state = m.get("state", "?")
		chk = check_health(m)
		chk_col = {"ok": green, "FAIL": red, "warn": yellow, "-": dim}.get(chk, yellow)(f"{chk:<4}")
		state_col = green(f"{state:<7}") if state == "started" else dim(f"{state:<7}")

		if state != "started":
			lines.append(f"{dim(mid):<14} {reg:<3} {state_col} {chk_col} {dim('(not polled)')}")
			continue

		data, err = results.get(mid, (None, "n/a"))
		if err:
			lines.append(
				f"{mid:<14} {reg:<3} {state_col} {chk_col} "
				f"{red('ERR ' + err)}"
			)
			continue

		reachable += 1
		pend = data.get("pending_tasks", 0)
		mx = data.get("max_pending_tasks", 0)
		slots = data.get("slots_in_use", 0)
		conc = data.get("concurrency", 0)
		proc = data.get("processing", 0)
		stall = data.get("stalled_in_gate", 0)
		queue = data.get("queued_for_slot", 0)
		ram = data.get("available_ram_mb")
		stgr = data.get("start_stagger_s")

		tot["pend"] += pend or 0
		tot["max"] += mx or 0
		tot["slots"] += slots or 0
		tot["conc"] += conc or 0
		tot["proc"] += proc or 0
		tot["stall"] += stall or 0
		tot["queue"] += queue or 0
		if ram is not None:
			rams.append(ram)
		for p in data.get("active_phases") or []:
			name = norm_phase(p.get("phase"))
			fleet_phases[name] = fleet_phases.get(name, 0) + 1

		pend_s = f"{pend}/{mx}"
		if mx and pend >= mx:
			pend_s = red(f"{pend_s:>7}")
		elif mx and pend >= 0.8 * mx:
			pend_s = yellow(f"{pend_s:>7}")
		else:
			pend_s = f"{pend_s:>7}"
		slot_s = f"{slots}/{conc}"
		stall_s = yellow(f"{stall:>5}") if stall else f"{stall:>5}"
		ram_s = "?" if ram is None else str(ram)
		ram_s = red(f"{ram_s:>6}") if (ram is not None and ram < 600) else f"{ram_s:>6}"
		stgr_s = "?" if stgr is None else (f"{stgr:g}")

		lines.append(
			f"{mid:<14} {reg:<3} {state_col} {chk_col} "
			f"{pend_s} {slot_s:>5} {proc:>4} {stall_s} {queue:>5} "
			f"{ram_s} {stgr_s:>5}  {phase_summary(data.get('active_phases'), phase_w)}"
		)

	# Footer totals.
	lines.append(dim("─" * min(term_w, len(HEADER))))
	ram_note = ""
	if rams:
		ram_note = f"  ram(min/avg)={min(rams)}/{int(sum(rams) / len(rams))}"
	lines.append(
		f"{bold('TOTAL')} {reachable} polled   "
		f"pend={tot['pend']}/{tot['max']}  "
		f"slots={tot['slots']}/{tot['conc']}  "
		f"proc={tot['proc']}  "
		f"stall={yellow(tot['stall']) if tot['stall'] else 0}  "
		f"queue={tot['queue']}{ram_note}"
	)
	if fleet_phases:
		hist = "  ".join(
			f"{name}×{n}" for name, n in sorted(fleet_phases.items(), key=lambda kv: -kv[1])
		)
		if len(hist) > term_w:
			hist = hist[: term_w - 1] + "…"
		lines.append(dim("phases: ") + hist)

	return "\n".join(lines)


def main():
	global _COLOR
	ap = argparse.ArgumentParser(description="Live fleet status for the hillview-worker Fly app.")
	ap.add_argument("--app", default=read_app_from_fly_toml() or DEFAULT_APP,
					help="Fly app name (default: from backend/fly.toml or %s)" % DEFAULT_APP)
	ap.add_argument("--interval", type=float, default=5.0, help="seconds between status polls (default 5)")
	ap.add_argument("--refresh-list", type=float, default=30.0,
					help="seconds between `fly status` machine-list refreshes (default 30)")
	ap.add_argument("--timeout", type=float, default=8.0, help="per-request HTTP timeout (default 8)")
	ap.add_argument("--endpoint", default="/status", help="worker endpoint to poll (default /status)")
	ap.add_argument("--base-url", default=None, help="override base URL (default https://<Hostname> from fly status)")
	ap.add_argument("--once", action="store_true", help="print a single snapshot and exit")
	ap.add_argument("--no-color", action="store_true", help="disable ANSI colour")
	args = ap.parse_args()

	if args.no_color:
		_COLOR = False

	machines = []
	base_url = args.base_url
	list_fetched_at = 0.0

	try:
		while True:
			# Refresh the machine list on first run, on schedule, or on demand.
			if not machines or (time.monotonic() - list_fetched_at) >= args.refresh_list:
				try:
					status = fly_status(args.app)
					machines = status.get("Machines", []) or []
					if base_url is None:
						host = status.get("Hostname")
						base_url = f"https://{host}" if host else None
					list_fetched_at = time.monotonic()
				except RuntimeError as e:
					if not machines:
						print(red(f"fly status failed: {e}"), file=sys.stderr)
						return 1
					print(red(f"fly status refresh failed (keeping stale list): {e}"), file=sys.stderr)

			if base_url is None:
				print(red("could not determine base URL (no Hostname); pass --base-url"), file=sys.stderr)
				return 1

			started = [m for m in machines if m.get("state") == "started"]
			results = {}
			if started:
				with ThreadPoolExecutor(max_workers=min(16, len(started))) as ex:
					futs = {
						ex.submit(poll_status, base_url, args.endpoint, m["id"], args.timeout): m["id"]
						for m in started
					}
					for fut in futs:
						mid = futs[fut]
						try:
							results[mid] = fut.result()
						except Exception as e:  # noqa: BLE001 - surface any straggler as a row error
							results[mid] = (None, type(e).__name__)

			frame = render(args.app, base_url, machines, results, time.monotonic() - list_fetched_at)
			if args.once:
				print(frame)
				return 0
			# Home cursor + clear to end of screen (smoother than full wipe).
			sys.stdout.write("\x1b[H\x1b[J" + frame + "\n")
			sys.stdout.flush()
			time.sleep(args.interval)
	except KeyboardInterrupt:
		print()
		return 0


if __name__ == "__main__":
	sys.exit(main())
