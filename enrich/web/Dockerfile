# Production build of the workbench UI (adapter-node, self-contained bundle).
# A built server, not `vite dev`: no file watchers, small stable memory — what
# you want running unattended. Dev loop stays `bun run dev` on the host
# (stop this container first; both want :8071).
#
# Build context is the REPO ROOT (enrich/docker-compose.yml) because the UI
# imports shared zoomview modules from repo-root shared/zoomview — the
# $zoomview alias resolves ../../shared/… relative to the config, so the
# shared dir is COPYied to /shared/… (two levels up from /app = /).
# Dockerfile.dockerignore allowlists just the two trees.
FROM oven/bun:1 AS build
WORKDIR /app
COPY enrich/web/package.json enrich/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY enrich/web/ .
COPY shared/zoomview /shared/zoomview
COPY shared/terrain /shared/terrain
# Serve the whole app under a path prefix. BUILD time, not run time: SvelteKit bakes the
# base into every emitted asset URL, so it cannot be changed by restarting the container.
ARG BASE_PATH=""
ENV BASE_PATH=${BASE_PATH}
RUN bun run build

FROM oven/bun:1
WORKDIR /app
COPY --from=build /app/build ./build
ENV PORT=8071
EXPOSE 8071
CMD ["bun", "build/index.js"]
