"""Where the stack lives, per machine and per way of reaching it.

Each profile is the full set of host-bearing declarations for one (machine ×
reachability) combination. `scripts/set_host.py` renders one into the env files.

This module is the CODE: the profile shape, the VM template, and how a machine
picks its profile. The DATA — which machines exist, their addresses and names —
is per-deployment and stays out of git, in the first of:

    <repo>/hosts.toml
    ~/.config/hillview/hosts.toml      (one copy shared by every worktree)

`hosts.example.toml` documents the format. With neither file present the only
profile is the built-in `localhost`, which is what a fresh clone or a sandbox
gets — so the stack and the test runner work there without any setup.

Why profiles rather than "swap the hostname": the modes differ by scheme, port
AND path, not just host — Caddy fronts the worker on its own port (docker-proxy
already owns 8056 on IPv4) and serves the pics volumes under /pics and /pics2,
where the bare file server serves them off its root.

And why the browser/internal split: a `*-ygg` name can be reachable from other
devices while ygg does not run inside the box serving it. So a value the
BROWSER resolves and a value a CONTAINER resolves are no longer the same string.
Keys are grouped by which one dereferences them.

  browser-facing   VITE_BACKEND, PICS_URL, WORKER_URL, FRONTEND_URL
                   WORKER_URL is in this group because the upload client talks
                   to the worker directly — see the Caddyfile note on fronting
                   it over plain HTTP so that client need not trust the
                   internal CA.
  internal         BACKEND_INTERNAL_URL (SSR -> api, inside the box)
                   Never rewritten: localhost is correct in every profile.

Reachability and what serves the frontend are separate things, and a profile
only fixes the first. A `*-raw` profile reaches the dev server on :8212 and the
built container on :3000 equally well — plain HTTP does not care which. So the
profile does not pick one: it leaves FRONTEND_URL undeclared, Playwright spawns
the dev server, and the container is a per-run override that already works:

    FRONTEND_URL=http://localhost:3000 ./run_tests.sh

An explicit env var beats the generated block, so that needs no support here.
A Caddy profile is different only because its origin IS the profile — the vhost
catch-all fronts :3000, so there is nothing left to choose.
"""
import json
import os
import sys
import tomllib
from typing import NoReturn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOSTS_FILES = (
	os.path.join(REPO, "hosts.toml"),
	os.path.expanduser("~/.config/hillview/hosts.toml"),
)

# Values nobody has pinned down yet. set_host refuses to apply a profile that
# still contains one, rather than writing a plausible-looking wrong URL.
UNSET = "<fill-in>"

# Every service on its own localhost port, plain HTTP — the ports .env.example
# declares. Always present, and the web leg's fallback on a machine hosts.toml
# does not name, so a fresh clone can run the suite (with the HTTP/1.1 flake
# warning) instead of dying on "no profile for this host". A hosts.toml may
# redefine it.
LOCALHOST = "localhost"
LOCALHOST_PROFILE = {
	"summary": "every service on localhost, plain HTTP",
	"note": "built-in fallback for a machine hosts.toml does not name",
	"env": {
		"WORKER_URL": "http://localhost:8056",
		"PICS_URL": "http://localhost:9999/",
	},
	"frontend_env": {
		"VITE_BACKEND": "http://localhost:8055/api",
		"VITE_UMAMI_URL": "http://localhost:3344",
	},
	"pools": {"/app/pics": "http://localhost:9999/"},
}

# set_host.verify() reads these, so a profile without them fails on load rather
# than halfway through a switch.
REQUIRED_ENV = ("WORKER_URL", "PICS_URL")


def vm_profiles(machine, ip, local_host, ygg_host, ygg_reachable_locally=False, env=None):
	"""The standard three profiles for one of the dev VMs.

	The VMs are clones of each other, so everything except the name and the
	address is identical: same ports (api 8055, worker 8056, frontend 3000,
	umami 3344, pics file-server 9999), same Caddy path shapes, and a single
	files-pool at /app/pics because none of them declares FILE_POOLS.

	Written out per machine, that is three near-identical blocks each time a VM
	is cloned. Generated instead, adding a box is one hosts.toml entry — and the
	shapes cannot drift apart by accident, which is how one VM's `local` vhost
	once ended up without the /umami route its ygg vhost had.

	`env` is extra api/worker declarations the machine carries in every profile
	(e.g. PANORAMAX_BASE_URL), merged over the template's.
	"""
	extra = {"PANORAMAX_SCOPE": "p1", **(env or {})}

	def caddy(host, frontend_url, **more):
		return {
			"env": {
				"WORKER_URL": f"https://{host}/worker",
				"PICS_URL": f"https://{host}/pics/",
				**extra,
			},
			"frontend_env": {
				"VITE_BACKEND": f"https://{host}/api",
				"VITE_UMAMI_URL": f"https://{host}/umami",
			},
			"pools": {"/app/pics": f"https://{host}/pics/"},
			"frontend_url": frontend_url,
			**more,
		}

	return {
		f"{machine}-raw": {
			"summary": f"{machine}, every service on its own port, plain HTTP",
			"note": f"Android against {machine}",
			"env": {
				"WORKER_URL": f"http://{ip}:8056",
				# The :9999 vhost roots its catch-all at /pics, so the server
				# root IS the pics root.
				"PICS_URL": f"http://{ip}:9999/",
				**extra,
			},
			"frontend_env": {"VITE_BACKEND": f"http://{ip}:8055/api"},
			"pools": {"/app/pics": f"http://{ip}:9999/"},
			"frontend_url": None,
		},
		f"{machine}-local": dict(
			summary=f"{machine}'s own Caddy, single h2 origin, reachable on the LAN",
			note=f"Playwright on {machine}",
			**caddy(local_host, f"https://{local_host}"),
		),
		f"{machine}-ygg": dict(
			summary=f"{machine} published over Yggdrasil, for interactive testing from another device",
			note="Terminated elsewhere, which proxies in. "
			     + ("This box resolves the name to itself, so it works locally too."
			        if ygg_reachable_locally else
			        "ygg does not run inside this box, so only other devices can use it."),
			**caddy(ygg_host, None, reachable_locally=ygg_reachable_locally),
		),
	}


def hosts_file():
	"""The hosts.toml in force, or None."""
	for path in HOSTS_FILES:
		if os.path.exists(path):
			return path
	return None


def _fail(path, message) -> NoReturn:
	sys.exit(f"host_profiles: {path}: {message}")


def load_profiles(path):
	"""Built-in profiles, plus everything `path` declares (None: built-ins only)."""
	profiles = {LOCALHOST: dict(LOCALHOST_PROFILE)}
	config = {}
	if path is not None:
		try:
			with open(path, "rb") as handle:
				config = tomllib.load(handle)
		except tomllib.TOMLDecodeError as err:
			_fail(path, f"not valid TOML ({err})")

	template = config.get("vm_template", {})
	for machine, vm in config.get("vm", {}).items():
		try:
			profiles.update(vm_profiles(
				machine,
				vm["ip"],
				local_host=template["local"].format(machine=machine),
				ygg_host=template["ygg"].format(machine=machine),
				ygg_reachable_locally=vm.get("ygg_reachable_locally", False),
				env=vm.get("env"),
			))
		except KeyError as err:
			_fail(path, f"[vm.{machine}] needs {err} (and [vm_template] needs local and ygg)")

	for name, profile in config.get("profiles", {}).items():
		profiles[name] = profile

	for name, profile in profiles.items():
		missing = [f"env.{key}" for key in REQUIRED_ENV if key not in profile.get("env", {})]
		missing += [key for key in ("summary", "frontend_env", "pools") if key not in profile]
		if missing:
			_fail(path, f"profile {name!r} is missing {', '.join(missing)}")
		# TOML has no null, so an absent frontend_url is how a file says None.
		profile.setdefault("frontend_url", None)
		profile.setdefault("note", "")
	return profiles


HOSTS_FILE = hosts_file()
PROFILES = load_profiles(HOSTS_FILE)


# Picking a profile for a job needs no per-machine table — the name carries it.
# Profiles are <machine>-<suffix>, and the suffixes have fixed meanings:
#
#   raw     every service on its own port over plain HTTP. What Android uses,
#           being the only thing that will not trip over Caddy's internal CA.
#   local   an h2 origin this machine serves and can reach itself.
#   ygg     an h2 origin published over Yggdrasil. Whether the machine it serves
#           can ALSO reach it varies, so the profile says so outright with
#           `reachable_locally` rather than leaving it to be inferred.
#
# Driving a browser wants an h2 origin either way — plain HTTP/1.1 starves chunk
# loads into the stalled-request flake class.
#
# ygg first: it is the canonical origin, the one name that works from anywhere.
# `local` is the fallback for a box that cannot reach its own ygg name. The
# reachable_locally flag is what makes this ordering safe, and it means a box
# that later CAN resolve its own ygg name starts preferring it with no change
# here.
WEB_SUFFIXES = ("ygg", "local")


def profile_for(hostname, leg):
	"""Profile this machine should use for the `web` or `android` leg, or None.

	The web leg falls back to `localhost` for a machine with no profiles of its
	own; android does not, since a device cannot reach the host's localhost.
	"""
	if leg == "android":
		name = f"{hostname}-raw"
		return name if name in PROFILES else None
	for suffix in WEB_SUFFIXES:
		profile = PROFILES.get(f"{hostname}-{suffix}")
		# raw/local are reachable by definition; only ygg ever says otherwise.
		if profile and profile.get("reachable_locally", True):
			return f"{hostname}-{suffix}"
	return LOCALHOST


def unset_keys(profile):
	"""Every key in `profile` still left at UNSET, as readable dotted paths."""
	missing = []
	for section in ("env", "frontend_env", "pools"):
		for key, value in profile.get(section, {}).items():
			if value == UNSET:
				missing.append(f"{section}.{key}")
	return missing


def android_backends():
	"""The API of every `-raw` profile, as presets for the Android app's API-URL menu.

	All of them, not just this machine's: the box that builds the APK is not
	necessarily the one the phone uploads to, and the menu is where the phone
	picks. A profile whose VITE_BACKEND is still UNSET is left out, as set_host
	would refuse it.

	frontend2's Gradle build reads this as JSON (run this file as a script)
	rather than parsing hosts.toml itself, so the vm template expands here and
	nowhere else.
	"""
	backends = []
	for name, profile in PROFILES.items():
		if not name.endswith("-raw"):
			continue
		url = profile["frontend_env"].get("VITE_BACKEND")
		if url and url != UNSET:
			backends.append({"label": name, "apiUrl": url})
	return backends


if __name__ == "__main__":
	if sys.argv[1:] != ["android-backends"]:
		sys.exit("usage: host_profiles.py android-backends")
	print(json.dumps(android_backends()))
