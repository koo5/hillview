#!/usr/bin/env bash
# Serve a vips dzsave pyramid locally with an OpenSeadragon viewer.
#
# Writes viewer.html + a minimal Caddyfile to a fresh scratch dir under
# $HOME/.cache/dz_view/ and runs caddy in docker to serve on HTTPS with
# HTTP/2. HTTP/2 multiplexing beats the browser's 6-request-per-host cap
# you hit on HTTP/1.1, which makes a big difference when scrolling a
# gigapixel pyramid. Falls back to python3's built-in HTTP/1.1 server if
# docker isn't installed. The scratch dir is removed on Ctrl-C.
#
# Scratch dir lives under $HOME (not /tmp) because snap-packaged docker
# cannot reliably bind-mount /tmp paths into containers.
#
# Usage:
#   dz_view.sh <prefix-or-dzi> [port]
#
# Example:
#   vips dzsave pano.exr pano_dz --suffix=.webp[Q=85]
#   dz_view.sh pano_dz
#   # -> open https://localhost:8000/viewer.html
#
# First visit (caddy path): browser will warn about caddy's self-signed
# cert — accept. The cert is persisted in the `dz_view_caddy_data`
# docker volume so subsequent runs reuse it; no re-warning.
#
# Uses OSD's Image-descriptor tileSources form rather than the .dzi URL
# string, because OpenSeadragon's DziTileSource refuses WebP-based DZIs
# ("Sorry, we don't support WEBP-based Deep Zoom Images"). Mirrors the
# pattern in frontend/.../OpenSeadragonViewer.svelte.

set -euo pipefail

PREFIX="${1:?usage: $0 <prefix-or-dzi> [port]}"
# Ask the OS for an ephemeral free port if the caller didn't pick one.
# Tiny TOCTOU window between close() and bind() — fine for dev use.
PORT="${2:-$(python3 -c 'import socket;s=socket.socket();s.bind(("",0));print(s.getsockname()[1]);s.close()')}"
PREFIX="${PREFIX%.dzi}"

DZI="${PREFIX}.dzi"
FILES_DIR="${PREFIX}_files"
if [ ! -f "$DZI" ]; then
    echo "error: $DZI not found" >&2
    exit 2
fi

DZI_ABS="$(realpath -- "$DZI")"
FILES_ABS=""
if [ -d "$FILES_DIR" ]; then
    FILES_ABS="$(realpath -- "$FILES_DIR")"
fi

PREFIX_BASE="$(basename -- "$PREFIX")"
DZI_BASE="${PREFIX_BASE}.dzi"

CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/dz_view"
mkdir -p "$CACHE_ROOT"
TMPDIR="$(mktemp -d -p "$CACHE_ROOT" "${PREFIX_BASE}.XXXXXX")"
trap 'rm -rf -- "$TMPDIR"' EXIT

FILES_BASE="${PREFIX_BASE}_files"

HAS_DOCKER=0
command -v docker >/dev/null 2>&1 && HAS_DOCKER=1

# When using docker, stage everything under $TMPDIR/srv so we can use
# directory-only bind mounts (single-file bind mounts from /tmp break
# under the snap-packaged docker).
if [ "$HAS_DOCKER" = 1 ]; then
    mkdir -p "$TMPDIR/srv/$FILES_BASE" "$TMPDIR/caddy"
    SRV_DIR="$TMPDIR/srv"
else
    SRV_DIR="$TMPDIR"
fi

cat > "$SRV_DIR/viewer.html" <<HTML
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${PREFIX_BASE}</title>
  <style>html,body,#v{margin:0;height:100vh;background:#111}</style>
</head>
<body>
  <div id="v"></div>
  <script src="https://cdn.jsdelivr.net/npm/openseadragon@4/build/openseadragon/openseadragon.min.js"></script>
  <script>
    const dziUrl = "${DZI_BASE}";
    const filesUrl = dziUrl.replace(/\.dzi\$/, "_files/");
    fetch(dziUrl).then(r => r.text()).then(xml => {
      const d = new DOMParser().parseFromString(xml, "application/xml");
      const img = d.querySelector("Image");
      const sz = d.querySelector("Size");
      OpenSeadragon({
        id: "v",
        prefixUrl: "https://cdn.jsdelivr.net/npm/openseadragon@4/build/openseadragon/images/",
        maxZoomPixelRatio: 4,
        imageLoaderLimit: 0,
        maxImageCacheCount: 500,
        tileSources: {
          Image: {
            xmlns: "http://schemas.microsoft.com/deepzoom/2008",
            Url: filesUrl,
            Format: img.getAttribute("Format"),
            Overlap: img.getAttribute("Overlap"),
            TileSize: img.getAttribute("TileSize"),
            Size: {
              Width: sz.getAttribute("Width"),
              Height: sz.getAttribute("Height"),
            },
          },
        },
      });
    });
  </script>
</body>
</html>
HTML

# Put the branching serve logic in a function so bash parses it fully up
# front. If the script file gets touched mid-run (editor autosave, linter),
# bash's line-by-line read can otherwise land in the wrong branch.
serve() {
    if [ "$HAS_DOCKER" = 1 ]; then
        # Small DZI XML: copy into the staged srv dir (cheap).
        # _files dir: bind-mount so we don't duplicate gigabytes.
        cp -- "$DZI_ABS" "$SRV_DIR/$DZI_BASE"

        # TLS strategy: prefer mkcert-issued cert (no browser warning once
        # `mkcert -install` has seeded the local CA into the system +
        # Firefox trust stores). Fall back to caddy's internal CA (one
        # cert-warning click per fresh Firefox profile).
        local TLS_DIRECTIVE="tls internal"
        local USE_MKCERT=0
        local CERT_DIR="$CACHE_ROOT/certs"
        if command -v mkcert >/dev/null 2>&1; then
            if [ ! -f "$CERT_DIR/localhost.pem" ] || [ ! -f "$CERT_DIR/localhost-key.pem" ]; then
                mkdir -p "$CERT_DIR"
                echo "dz_view: first-time mkcert setup"
                if ! command -v certutil >/dev/null 2>&1; then
                    echo "  NOTE: certutil missing — Firefox won't get the CA."
                    echo "        apt install libnss3-tools, then rerun with the cert files removed:"
                    echo "        rm -f $CERT_DIR/localhost*.pem"
                fi
                mkcert -install || echo "dz_view: mkcert -install failed; continuing with whatever trust store state we've got"
                mkcert -cert-file "$CERT_DIR/localhost.pem" \
                       -key-file  "$CERT_DIR/localhost-key.pem" \
                       localhost 127.0.0.1 ::1
            fi
            USE_MKCERT=1
            TLS_DIRECTIVE="tls /certs/localhost.pem /certs/localhost-key.pem"
        fi

        cat > "$TMPDIR/caddy/Caddyfile" <<CFG
{
    admin off
    auto_https disable_redirects
}
localhost:${PORT} {
    ${TLS_DIRECTIVE}
    root * /srv
    file_server
    encode gzip
}
CFG
        local -a MOUNTS=(
            -v "$SRV_DIR:/srv"
            -v "$TMPDIR/caddy:/etc/caddy:ro"
        )
        [ "$USE_MKCERT" = 1 ] && MOUNTS+=(-v "$CERT_DIR:/certs:ro")
        [ -n "$FILES_ABS" ] && MOUNTS+=(-v "$FILES_ABS:/srv/$FILES_BASE:ro")
        if [ "$USE_MKCERT" = 1 ]; then
            echo "serving via caddy (docker, mkcert cert)   OPEN: https://localhost:${PORT}/viewer.html"
        else
            echo "serving via caddy (docker, internal cert) OPEN: https://localhost:${PORT}/viewer.html"
            echo "(browser will warn; install mkcert + libnss3-tools for silent operation:"
            echo "   sudo apt install mkcert libnss3-tools )"
        fi
        echo
        echo ---------
        echo
        docker run --rm \
            -p "${PORT}:${PORT}" \
            "${MOUNTS[@]}" \
            -v dz_view_caddy_data:/data \
            -v dz_view_caddy_config:/config \
            caddy:latest
    else
        ln -s -- "$DZI_ABS" "$SRV_DIR/$DZI_BASE"
        [ -n "$FILES_ABS" ] && ln -s -- "$FILES_ABS" "$SRV_DIR/$FILES_BASE"
        echo "docker not found; using python3 -m http.server (HTTP/1.1, slower)"
        echo "OPEN: http://localhost:${PORT}/viewer.html"
        cd "$SRV_DIR"
        python3 -m http.server "$PORT"
    fi
}

serve
exit $?
