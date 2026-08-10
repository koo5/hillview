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

PROFILES = {
	# ---- this machine ---------------------------------------------------
	"jj-raw": {
		"summary": "every service on its own port, plain HTTP, LAN IP",
		"note": "the only mode Android can use — it will not trust Caddy's internal CA",
		"env": {
			"WORKER_URL": "http://10.0.0.24:8056",
			"PICS_URL": "http://10.0.0.24:9999/",
		},
		"frontend_env": {
			"VITE_BACKEND": "http://10.0.0.24:8055/api",
		},
		# container path -> URL serving it, for the files pools in FILE_POOLS
		"pools": {
			"/app/pics2": "http://10.0.0.24:9999/pics2/",
			"/app/pics": "http://10.0.0.24:9999/",
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
		},
		# Not a choice: the origin IS the profile, and its catch-all fronts :3000.
		"frontend_url": "https://hv.jj.internal",
	},

	# ---- dev4 (the VM), at 192.168.122.64 --------------------------------
	# dev4 declares NO FILE_POOLS, so it runs the single-pool fallback from
	# PICS_URL/PICS_DIR and writes to /app/pics. Hence one pool entry and no
	# /pics2 anywhere — pics2 is this machine's multi-pool setup and does not
	# transfer. set_host skips `pools` entirely while FILE_POOLS is absent, so
	# the entry is only insurance for the day dev4 grows one.
	"dev4-raw": {
		"summary": "dev4, every service on its own port, plain HTTP",
		"note": "Android against dev4",
		"env": {
			"WORKER_URL": "http://192.168.122.64:8056",
			# dev4's :9999 vhost roots its catch-all at /pics, so the bare
			# server root IS the pics root — same shape as this machine's.
			"PICS_URL": "http://192.168.122.64:9999/",
		},
		"frontend_env": {
			"VITE_BACKEND": "http://192.168.122.64:8055/api",
		},
		"pools": {
			"/app/pics": "http://192.168.122.64:9999/",
		},
		# The origin Playwright targets. None => no declaration => it spawns
		# `bun run dev` on :8212 itself. Plain HTTP reaches the built container
		# on :3000 just as well; that is a per-run override, not a profile —
		#   FRONTEND_URL=http://localhost:3000 ./run_tests.sh
		# still wins over this block, so it needs no knob here.
		"frontend_url": None,
	},
	"dev4-local": {
		"summary": "dev4's own Caddy, single h2 origin, reachable on the LAN",
		"note": "Playwright on dev4. NEEDS the hv. rename on dev4 first — its vhost "
		        "is still named hillview.dev4.local, so these point at a name "
		        "nothing answers until that lands.",
		"env": {
			"WORKER_URL": "https://hv.dev4.local/worker",
			"PICS_URL": "https://hv.dev4.local/pics/",
		},
		"frontend_env": {
			"VITE_BACKEND": "https://hv.dev4.local/api",
			"VITE_UMAMI_URL": "https://hv.dev4.local/umami",
		},
		"pools": {
			"/app/pics": "https://hv.dev4.local/pics/",
		},
		"frontend_url": "https://hv.dev4.local",
	},
	"dev4-ygg": {
		"summary": "dev4 published over Yggdrasil, for interactive testing from another device",
		"note": "NOT a Playwright target. ygg does not run inside dev4, so only the "
		        "browser-facing keys carry the ygg host; a jj Caddy section proxies in.",
		"env": {
			"WORKER_URL": "https://hv.dev4.jj.internal/worker",
			"PICS_URL": "https://hv.dev4.jj.internal/pics/",
		},
		"frontend_env": {
			"VITE_BACKEND": "https://hv.dev4.jj.internal/api",
			"VITE_UMAMI_URL": "https://hv.dev4.jj.internal/umami",
		},
		"pools": {
			"/app/pics": "https://hv.dev4.jj.internal/pics/",
		},
		# Interactive testing only — never a Playwright target.
		"frontend_url": None,
	},
}


def unset_keys(profile):
	"""Every key in `profile` still left at UNSET, as readable dotted paths."""
	missing = []
	for section in ("env", "frontend_env", "pools"):
		for key, value in profile.get(section, {}).items():
			if value == UNSET:
				missing.append(f"{section}.{key}")
	return missing
