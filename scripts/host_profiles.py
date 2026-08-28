"""Where the stack lives, per machine and per way of reaching it.

Each profile is the full set of host-bearing declarations for one (machine ×
reachability) combination. `scripts/set_host.py` renders one into the env files.

Why profiles rather than "swap the hostname": the modes differ by scheme, port
AND path, not just host — Caddy fronts the worker on its own port (docker-proxy
already owns 8056 on IPv4) and serves the pics volumes under /pics and /pics2,
where the bare file server serves them off its root.

And why the browser/internal split: `dev4-ygg` is reachable over Yggdrasil from
other devices, but ygg does not run inside dev4 and won't. So a value the
BROWSER resolves and a value a CONTAINER resolves are no longer the same string.
Keys are grouped below by which one dereferences them.

  browser-facing   VITE_BACKEND, PICS_URL, WORKER_URL, FRONTEND_URL
                   WORKER_URL is in this group because the upload client talks
                   to the worker directly — see the Caddyfile note on fronting
                   it over plain HTTP so that client need not trust the
                   internal CA.
  internal         BACKEND_INTERNAL_URL (SSR -> api, inside the box)
                   Never rewritten: localhost is correct in every profile.

Reachability and what serves the frontend are separate things, and a profile
only fixes the first. `jj-raw` reaches the dev server on :8212 and the built
container on :3000 equally well — plain HTTP does not care which. So the profile
does not pick one: it leaves FRONTEND_URL undeclared, Playwright spawns the dev
server, and the container is a per-run override that already works:

    FRONTEND_URL=http://localhost:3000 ./run_tests.sh

An explicit env var beats the generated block, so that needs no support here.
A Caddy profile is different only because its origin IS the profile — the vhost
catch-all fronts :3000, so there is nothing left to choose.
"""

# Values nobody has pinned down yet. set_host refuses to apply a profile that
# still contains one, rather than writing a plausible-looking wrong URL.
UNSET = "<fill-in>"

def vm_profiles(machine, ip, ygg_reachable_locally=False):
	"""The standard three profiles for one of the dev VMs.

	The VMs are clones of each other, so everything except the name and the
	address is identical: same ports (api 8055, worker 8056, frontend 3000,
	umami 3344, pics file-server 9999), same Caddy path shapes, and a single
	files-pool at /app/pics because none of them declares FILE_POOLS.

	Written out per machine, that is three near-identical blocks each time a VM
	is cloned. Generated instead, adding a box is one line — and the shapes
	cannot drift apart by accident, which is how dev4's `local` vhost ended up
	without the /umami route its ygg vhost had.

	jj is deliberately NOT built from this: it has no `local` profile at all, it
	is on a different network, and it carries a real multi-pool FILE_POOLS with
	a second pics2 pool. Forcing it through the template would mean parameters
	that only ever take one value.
	"""
	local, ygg = f"hv.{machine}.local", f"hv.{machine}.jj.internal"

	def caddy(host, frontend_url, **extra):
		return {
			"env": {
				"WORKER_URL": f"https://{host}/worker",
				"PICS_URL": f"https://{host}/pics/",
			},
			"frontend_env": {
				"VITE_BACKEND": f"https://{host}/api",
				"VITE_UMAMI_URL": f"https://{host}/umami",
			},
			"pools": {"/app/pics": f"https://{host}/pics/"},
			"frontend_url": frontend_url,
			**extra,
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
			},
			"frontend_env": {"VITE_BACKEND": f"http://{ip}:8055/api"},
			"pools": {"/app/pics": f"http://{ip}:9999/"},
			"frontend_url": None,
		},
		f"{machine}-local": dict(
			summary=f"{machine}'s own Caddy, single h2 origin, reachable on the LAN",
			note=f"Playwright on {machine}",
			**caddy(local, f"https://{local}"),
		),
		f"{machine}-ygg": dict(
			summary=f"{machine} published over Yggdrasil, for interactive testing from another device",
			note="Terminated on jj, which proxies in. "
			     + ("This box resolves the name to itself, so it works locally too."
			        if ygg_reachable_locally else
			        "ygg does not run inside this box, so only other devices can use it."),
			**caddy(ygg, None, reachable_locally=ygg_reachable_locally),
		),
	}
PROFILES = {
	# ---- this machine ---------------------------------------------------
	"jj-raw": {
		"summary": "every service on its own port, plain HTTP, LAN IP",
		"note": "the only mode Android can use — it will not trust Caddy's internal CA",
		"env": {
			"WORKER_URL": "http://10.0.0.24:8056",
			"PICS_URL": "http://10.0.0.24:9999/",
			# Base URL for artifacts kept in the worker's own uploads volume
			# (per-photo keep_pics_in_worker uploads; the toggle itself is
			# ALLOW_KEEP_PICS_IN_WORKER, deliberately NOT profile-managed).
			"WORKER_PICS_URL": "http://10.0.0.24:9999/wpics/",
			# name=url map for photo trees the worker may serve IN PLACE (external
			# pyramids offered via --pyramid; dev-only, Caddy mounts the archive
			# read-only at /apics). Names are the LOCAL_PHOTO_ROOTS root names
			# from .env (mounted at /external-data/<name> in the worker).
			"LOCAL_PHOTO_URLS": "autocopy=http://10.0.0.24:9999/apics/",
		},
		"frontend_env": {
			"VITE_BACKEND": "http://10.0.0.24:8055/api",
		},
		# container path -> URL serving it, for the files pools in FILE_POOLS
		"pools": {
			"/app/pics2": "http://10.0.0.24:9999/pics2/",
			"/app/pics": "http://10.0.0.24:9999/",
			# The worker's uploads volume, mounted into the api container at
			# /app/wuploads so deleting a kept photo can remove its files.
			"/app/wuploads": "http://10.0.0.24:9999/wpics/",
		},
		# The origin Playwright targets. None => no declaration => it spawns
		# `bun run dev` on :8212 itself. Plain HTTP reaches the built container
		# on :3000 just as well; that is a per-run override, not a profile —
		#   FRONTEND_URL=http://localhost:3000 ./run_tests.sh
		# still wins over this block, so it needs no knob here.
		"frontend_url": None,
	},
	"jj-ygg": {
		"summary": "single HTTPS/HTTP-2 origin fronting frontend + /api + /pics + worker",
		"note": "wanted for Playwright: h2 removes the ~6-connections-per-origin "
		        "cap whose starvation causes the suite's stalled-request flakes",
		"env": {
			# NOT the plain-http :8456 route — that one exists for the CLI
			# uploader, which would otherwise have to trust the internal CA. A
			# browser on an https page cannot fetch it at all: active mixed
			# content is blocked by scheme, so the upload dies as "Failed to
			# fetch". Browsers get a same-origin path route instead.
			# No trailing slash: the client builds `${WORKER_URL}/upload_async`.
			"WORKER_URL": "https://hv.jj.internal/worker",
			"PICS_URL": "https://hv.jj.internal/pics/",
			# Base URL for artifacts kept in the worker's own uploads volume
			# (per-photo keep_pics_in_worker uploads; the toggle itself is
			# ALLOW_KEEP_PICS_IN_WORKER, deliberately NOT profile-managed).
			"WORKER_PICS_URL": "https://hv.jj.internal/wpics/",
			# name=url map for photo trees the worker may serve IN PLACE (external
			# pyramids offered via --pyramid; dev-only, Caddy mounts the archive
			# read-only at /apics). Names are the LOCAL_PHOTO_ROOTS root names
			# from .env (mounted at /external-data/<name> in the worker).
			"LOCAL_PHOTO_URLS": "autocopy=https://hv.jj.internal/apics/",
		},
		"frontend_env": {
			"VITE_BACKEND": "https://hv.jj.internal/api",
			# Analytics is browser-facing too. Left on localhost it is fetched
			# from an https page against the loopback address space, which Chrome
			# refuses under Private Network Access — a console error on EVERY page
			# load, which fails every test that asserts a clean console. Routed
			# through the same origin it is same-origin, so no CORS either.
			# No trailing slash: umami derives /api/send from its script src.
			"VITE_UMAMI_URL": "https://hv.jj.internal/umami",
		},
		"pools": {
			"/app/pics2": "https://hv.jj.internal/pics2/",
			"/app/pics": "https://hv.jj.internal/pics/",
			# The worker's uploads volume, mounted into the api container at
			# /app/wuploads so deleting a kept photo can remove its files.
			"/app/wuploads": "https://hv.jj.internal/wpics/",
		},
		# Not a choice: the origin IS the profile, and its catch-all fronts :3000.
		"frontend_url": "https://hv.jj.internal",
		# jj's own Caddy serves this name and jj runs ygg, so jj can drive a
		# browser against it — which is why jj needs no `local` profile.
		"reachable_locally": True,
	},

	# ---- the dev VMs -----------------------------------------------------
	# Clones of one another, so they are generated rather than written out; see
	# vm_profiles above for what is shared and why jj is not included.
	#
	# dev4-3 arrived as a clone still calling itself `dev4`, which would have
	# made profile_for() hand it dev4's profiles and aim it at the wrong box.
	# Its hostname is now set persistently (cloud-init's preserve_hostname had
	# to be turned on, or it reverted every boot), and its own names resolve to
	# itself rather than to dev4.
	**vm_profiles("dev4", "192.168.122.64"),
	**vm_profiles("dev4-3", "192.168.122.31"),
	**vm_profiles("dev4-2", "192.168.122.37"),
}


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
# `local` is the fallback for a box that cannot reach its own ygg name, which is
# every VM — their ygg names are terminated on jj, and ygg does not run inside
# them. The reachable_locally flag is what makes this ordering safe, and it means
# a box that later CAN resolve its own ygg name starts preferring it with no
# change here.
WEB_SUFFIXES = ("ygg", "local")


def profile_for(hostname, leg):
	"""Profile this machine should use for the `web` or `android` leg, or None."""
	if leg == "android":
		name = f"{hostname}-raw"
		return name if name in PROFILES else None
	for suffix in WEB_SUFFIXES:
		profile = PROFILES.get(f"{hostname}-{suffix}")
		# raw/local are reachable by definition; only ygg ever says otherwise.
		if profile and profile.get("reachable_locally", True):
			return f"{hostname}-{suffix}"
	return None


def unset_keys(profile):
	"""Every key in `profile` still left at UNSET, as readable dotted paths."""
	missing = []
	for section in ("env", "frontend_env", "pools"):
		for key, value in profile.get(section, {}).items():
			if value == UNSET:
				missing.append(f"{section}.{key}")
	return missing
