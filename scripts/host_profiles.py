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
"""

# Values nobody has pinned down yet. set_host refuses to apply a profile that
# still contains one, rather than writing a plausible-looking wrong URL.
UNSET = "<fill-in>"

PROFILES = {
	# ---- this machine ---------------------------------------------------
	"here-raw": {
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
		# None => no declaration => Playwright spawns `bun run dev` on :8212 itself.
		"frontend_url": None,
	},
	"here-caddy": {
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
		"frontend_url": "https://hv.jj.internal",
	},

	# ---- dev4 (the VM) ---------------------------------------------------
	# Same three-way split. The URLs below still need pinning against dev4's own
	# Caddyfile and LAN address — they are UNSET rather than guessed.
	"dev4-raw": {
		"summary": "dev4, every service on its own port, plain HTTP",
		"note": "Android against dev4",
		"env": {
			"WORKER_URL": UNSET,
			"PICS_URL": UNSET,
		},
		"frontend_env": {
			"VITE_BACKEND": UNSET,
		},
		"pools": {
			"/app/pics2": UNSET,
			"/app/pics": UNSET,
		},
		"frontend_url": None,
	},
	"dev4-local": {
		"summary": "dev4's own Caddy, single h2 origin, reachable on the LAN",
		"note": "Playwright on dev4 — the origin playwright.config.ts already documents",
		"env": {
			"WORKER_URL": UNSET,
			"PICS_URL": UNSET,
		},
		"frontend_env": {
			"VITE_BACKEND": "https://hv.dev4.local/api",
		},
		"pools": {
			"/app/pics2": UNSET,
			"/app/pics": UNSET,
		},
		"frontend_url": "https://hv.dev4.local",
	},
	"dev4-ygg": {
		"summary": "dev4 published over Yggdrasil, for interactive testing from another device",
		"note": "NOT a Playwright target. ygg does not run inside dev4, so only the "
		        "browser-facing keys carry the ygg host; a jj Caddy section proxies in. "
		        "The worker needs a route too — the upload client reaches it directly.",
		"env": {
			# Intended value once dev4's jj section carries a worker route, by the
			# same handle_path pattern as here-caddy (a browser on https cannot
			# use a plain-http worker):
			#   https://hv.dev4.jj.internal/worker
			# Left UNSET until that route exists, so the guard keeps refusing.
			"WORKER_URL": UNSET,
			"PICS_URL": "https://hv.dev4.jj.internal/pics/",
		},
		"frontend_env": {
			"VITE_BACKEND": "https://hv.dev4.jj.internal/api",
		},
		"pools": {
			"/app/pics2": "https://hv.dev4.jj.internal/pics2/",
			"/app/pics": "https://hv.dev4.jj.internal/pics/",
		},
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
