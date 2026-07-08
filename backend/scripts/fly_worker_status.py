#!/usr/bin/env python3
"""Live fleet status for the hillview-worker Fly app.

Enumerates machines via `fly status --json`, then polls each machine's own
`/status` endpoint (the rich worker_status snapshot: pending queue, slots,
processing, stall, RAM, active phases) and renders it as a refreshing table.

Two data sources:
  edge (default) -- poll each started machine's /status through Fly's public
    edge via the `fly-force-instance-id` header. No WireGuard/ssh needed, but
    each poll is an HTTP request that resets the machine's idle timer (keeps it
    awake) and can't see a suspended machine. Good for an on-demand look.
  prometheus (--source prometheus) -- read the worker_* gauges from Fly's
    managed Prometheus (scraped over the private network from /metrics). Does
    NOT touch the machines, so it doesn't perturb suspend/autostart, and it
    surfaces event-loop lag. Needs a Fly token (FLY_API_TOKEN or `fly auth
    token`) and the org slug (--org, else taken from `fly status`).

Usage:
    ./fly_worker_status.py                      # edge poll, live loop
    ./fly_worker_status.py --once               # single snapshot, then exit
    ./fly_worker_status.py --source prometheus  # non-perturbing, from metrics
    ./fly_worker_status.py --app other-app

Only `started` machines are polled in edge mode -- suspended/stopped machines
are listed but not hit, so edge mode never autostarts a sleeping machine.
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
import urllib.parse
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


# --- Prometheus source (non-perturbing: reads scraped metrics, no machine hits)
PROM_METRIC_MAP = {
	"worker_pending_tasks": "pending_tasks",
	"worker_max_pending_tasks": "max_pending_tasks",
	"worker_concurrency": "concurrency",
	"worker_slots_in_use": "slots_in_use",
	"worker_queued_for_slot": "queued_for_slot",
	"worker_processing": "processing",
	"worker_stalled_in_gate": "stalled_in_gate",
	"worker_start_stagger_seconds": "start_stagger_s",
	"worker_available_ram_mb": "available_ram_mb",
	"worker_event_loop_lag_seconds": "event_loop_lag_s",
	"worker_inflight_http_requests": "inflight_requests",
}


def fly_auth_token():
	"""A Fly API token from the env or `fly auth token`."""
	tok = os.environ.get("FLY_API_TOKEN") or os.environ.get("FLY_ACCESS_TOKEN")
	if tok:
		return tok.strip()
	try:
		proc = subprocess.run(["fly", "auth", "token"], capture_output=True, text=True, timeout=15)
		if proc.returncode == 0 and proc.stdout.strip():
			return proc.stdout.strip()
	except (FileNotFoundError, subprocess.TimeoutExpired):
		pass
	raise RuntimeError("no Fly token: set FLY_API_TOKEN or run `fly auth token`")


def resolve_org(status, override):
	"""Org slug for the Prometheus URL: --org, else the fly status Organization."""
	if override:
		return override
	org = status.get("Organization")
	if isinstance(org, dict):
		return org.get("Slug") or org.get("ID") or org.get("Name")
	return org


def fetch_prometheus(prom_url, org, token, app, timeout):
	"""Query Fly's managed Prometheus for the worker_* gauges. Returns
	{instance_label -> data dict} shaped like a /status response so render() can
	consume it unchanged. Reads scraped data — never touches the machines."""
	query = '{__name__=~"worker_.*",app="%s"}' % app
	url = f"{prom_url.rstrip('/')}/prometheus/{org}/api/v1/query?query=" + urllib.parse.quote(query)
	req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "accept": "application/json"})
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		payload = json.loads(resp.read().decode())
	if payload.get("status") != "success":
		raise RuntimeError(f"prometheus query error: {payload.get('error') or payload.get('status')}")
	out = {}
	for series in payload.get("data", {}).get("result", []):
		metric = series.get("metric", {})
		inst = metric.get("instance")
		if not inst:
			continue
		try:
			val = float(series["value"][1])
		except (KeyError, ValueError, IndexError, TypeError):
			continue
		d = out.setdefault(inst, {"active_phases": []})
		name = metric.get("__name__")
		if name == "worker_phase_active":
			d["active_phases"].extend({"phase": metric.get("phase", "unknown")} for _ in range(int(val)))
		elif name in PROM_METRIC_MAP:
			key = PROM_METRIC_MAP[name]
			d[key] = val if key == "event_loop_lag_s" else int(val)
	return out


def match_metrics(by_inst, machine):
	"""Find a machine's series by instance label — machine id, else private ip,
	else any label containing the id (Fly's exact instance label can vary)."""
	mid = machine.get("id", "")
	return (by_inst.get(mid)
			or by_inst.get(machine.get("private_ip"))
			or next((v for k, v in by_inst.items() if mid and mid in str(k)), None))


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
	f"{'RAM':>6} {'STGR':>5} {'LAG':>5}  PHASES"
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

	fixed_w = 14 + 1 + 3 + 1 + 7 + 1 + 4 + 1 + 7 + 1 + 5 + 1 + 4 + 1 + 5 + 1 + 5 + 1 + 6 + 1 + 5 + 1 + 5 + 2
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
		lag = data.get("event_loop_lag_s")
		lag_s = "-" if lag is None else f"{lag:.2f}"
		lag_s = red(f"{lag_s:>5}") if (lag is not None and lag > 0.5) else f"{lag_s:>5}"

		lines.append(
			f"{mid:<14} {reg:<3} {state_col} {chk_col} "
			f"{pend_s} {slot_s:>5} {proc:>4} {stall_s} {queue:>5} "
			f"{ram_s} {stgr_s:>5} {lag_s}  {phase_summary(data.get('active_phases'), phase_w)}"
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
	ap.add_argument("--source", choices=("edge", "prometheus"), default="edge",
					help="edge = poll /status via the Fly edge (perturbs suspend); "
						 "prometheus = read worker_* metrics from Fly's Prometheus (non-perturbing)")
	ap.add_argument("--org", default=None, help="Fly org slug for Prometheus (default: from fly status)")
	ap.add_argument("--prom-url", default="https://api.fly.io", help="Fly Prometheus base URL")
	args = ap.parse_args()

	if args.no_color:
		_COLOR = False

	prom_token = None
	if args.source == "prometheus":
		try:
			prom_token = fly_auth_token()
		except RuntimeError as e:
			print(red(str(e)), file=sys.stderr)
			return 1

	machines = []
	base_url = args.base_url
	org = args.org
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
					org = resolve_org(status, args.org) or org
					list_fetched_at = time.monotonic()
				except RuntimeError as e:
					if not machines:
						print(red(f"fly status failed: {e}"), file=sys.stderr)
						return 1
					print(red(f"fly status refresh failed (keeping stale list): {e}"), file=sys.stderr)

			if args.source == "edge" and base_url is None:
				print(red("could not determine base URL (no Hostname); pass --base-url"), file=sys.stderr)
				return 1

			started = [m for m in machines if m.get("state") == "started"]
			results = {}
			if args.source == "prometheus":
				if not org:
					print(red("could not determine Fly org for Prometheus; pass --org"), file=sys.stderr)
					return 1
				try:
					by_inst = fetch_prometheus(args.prom_url, org, prom_token, args.app, args.timeout)
					for m in started:
						data = match_metrics(by_inst, m)
						results[m["id"]] = (data, None) if data else (None, "no metric")
				except Exception as e:  # noqa: BLE001 - keep looping on transient query errors
					print(red(f"prometheus query failed: {e}"), file=sys.stderr)
			elif started:
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

			src_label = base_url if args.source == "edge" else f"prometheus:{org}"
			frame = render(args.app, src_label, machines, results, time.monotonic() - list_fetched_at)
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
