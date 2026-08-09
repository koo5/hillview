# Repo-root `shared/` → real workspace package(s) — TODO

Status: **idea, not started** (written 2026-07-27, after the vite watcher
staleness episode — see interim fix below).

## Why

`shared/terrain` and `shared/zoomview` are consumed by BOTH apps
(`frontend/`, `enrich/web/`) through per-app plumbing that has to be kept in
sync by hand:

- alias in two spellings: frontend `svelte.config.js` `kit.alias`
  (`$terrain`, `$zoomview`) + generated tsconfig; enrich/web vite
  `resolve.alias` + manual tsconfig paths;
- per-app `server.fs.allow` entries for the out-of-root dirs;
- per-app `watch-repo-shared` vite plugins (added 2026-07-27) because vite's
  watcher doesn't cover out-of-root modules — without them, shared edits
  served stale transforms until a dev-server restart;
- Dockerfile `.dockerignore` allowlists + `COPY shared/...` in both images;
- frontend vitest reaches over with a `../shared/terrain/**` include.

As real linked workspace packages (`@hillview/terrain`, `@hillview/zoomview`)
vite treats them as first-class watched source, imports get one spelling,
types flow without manual paths, and every bullet above disappears.

## Sketch

1. `package.json` in each shared dir — name, `"type": "module"`, `exports`
   map pointing at the TS source (no build step; both consumers transpile TS
   themselves today).
2. Root `package.json` with bun `workspaces: ["frontend", "enrich/web",
   "shared/*"]`; app manifests gain `"@hillview/terrain": "workspace:*"` etc.
3. Replace `$terrain/...` / `$zoomview/...` imports with
   `@hillview/terrain/...`; delete kit.alias entries, vite aliases, tsconfig
   paths, `fs.allow` extras, and both `watch-repo-shared` plugins.
4. Dockerfiles (both already use repo-root contexts): COPY the workspace
   manifests + shared packages so `bun install` links them in-image; update
   the dockerignore allowlists.
5. Frontend vitest: keep the shared tests running (either keep the include
   or give the packages their own `bun test`/vitest entry).

## Risks / gotchas

- `frontend/tests-appium/` is deliberately its own package (own lockfile, fat
  dep tree — see frontend/CLAUDE.md); keep it OUT of the workspace.
- Lockfile migration: a root `bun.lock` supersedes `frontend/bun.lock` —
  docker layer caching and any CI keyed on lockfile paths need updating.
- Tauri/Android build scripts (`scripts/android/*.sh`) must survive the
  node_modules layout change (workspace hoisting) — compile-verify the debug
  APK build.
- enrich/web forces runes on with a `node_modules`-in-path exclusion; linked
  packages resolve through node_modules symlinks, so if shared/ ever grows
  `.svelte` files, check which side of that heuristic they land on (today
  it's TS-only — moot).
- dev4.local's `hillview_frontend` container is a static build with its own
  env baking (`VITE_TERRAIN_API` currently absent) — rebuild + retest that
  image, don't just check the dev servers.

## Definition of done

- One import spelling everywhere; zero alias/tsconfig/fs.allow/watch-plugin
  duplication left.
- Shared edits hot-invalidate in both dev servers with no custom plumbing.
- Green: frontend unit suite, frontend `bun run check`, bench Playwright
  suite, both docker builds, android debug build.

## Interim state (until this happens)

The `watch-repo-shared` plugins in `frontend/vite.config.ts` and
`enrich/web/vite.config.ts` solve the dev staleness; the alias plumbing
stays. Delete both plugins as part of this migration.
