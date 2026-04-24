#!/usr/bin/env python3
"""
Deep-zoom pyramid utility — serve locally or deploy to a remote web server.

Commands:
  view PREFIX [--port N]
	  Serve locally with HTTPS + HTTP/2 via caddy-in-docker (no browser
	  warning if mkcert + libnss3-tools are installed). Falls back to
	  python http.server (HTTP/1.1, no TLS) if docker isn't available.
	  PREFIX may include or omit the .dzi suffix.

  deploy PREFIX REMOTE [--dry-run]
	  rsync the pyramid (<prefix>.dzi, <prefix>_files/) plus a freshly
	  generated viewer.html to REMOTE. REMOTE is an rsync target like
	  user@host:/var/www/html/pano/. Remote dir must exist.

Both commands share build_viewer_html() — the viewer.html they serve /
deploy bypasses OpenSeadragon's DziTileSource (which refuses WebP-based
DZIs) by parsing the .dzi at runtime and handing OSD an Image-descriptor.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "dz_view"


def build_viewer_html(prefix_name: str) -> str:
	"""Return a standalone viewer.html referencing <prefix_name>.dzi + _files/."""
	return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{prefix_name}</title>
  <style>html,body,#v{{margin:0;height:100vh;background:#111}}</style>
</head>
<body>
  <div id="v"></div>
  <script src="https://cdn.jsdelivr.net/npm/openseadragon@4/build/openseadragon/openseadragon.min.js"></script>
  <script>
	fetch("{prefix_name}.dzi").then(r => r.text()).then(xml => {{
	  const d = new DOMParser().parseFromString(xml, "application/xml");
	  const img = d.querySelector("Image");
	  const sz = d.querySelector("Size");
	  OpenSeadragon({{
		id: "v",
		prefixUrl: "https://cdn.jsdelivr.net/npm/openseadragon@4/build/openseadragon/images/",
		maxZoomPixelRatio: 4,
		imageLoaderLimit: 0,
		maxImageCacheCount: 500,
		tileSources: {{
		  Image: {{
			xmlns: "http://schemas.microsoft.com/deepzoom/2008",
			Url: "{prefix_name}_files/",
			Format: img.getAttribute("Format"),
			Overlap: img.getAttribute("Overlap"),
			TileSize: img.getAttribute("TileSize"),
			Size: {{
			  Width: sz.getAttribute("Width"),
			  Height: sz.getAttribute("Height"),
			}},
		  }},
		}},
	  }});
	}});
  </script>
</body>
</html>
"""


def resolve_pyramid(prefix_arg: str) -> tuple[Path, Path | None, str]:
	"""Given a user-supplied prefix (with or without .dzi), return
	(dzi_path, files_dir_or_None, prefix_name)."""
	p = Path(prefix_arg)
	if p.suffix == ".dzi":
		dzi = p
		prefix_name = p.stem
	else:
		dzi = p.with_name(f"{p.name}.dzi")
		prefix_name = p.name
	if not dzi.is_file():
		sys.exit(f"error: {dzi} not found")
	files_dir = dzi.parent / f"{prefix_name}_files"
	return dzi.resolve(), files_dir.resolve() if files_dir.is_dir() else None, prefix_name


def pick_free_port() -> int:
	s = socket.socket()
	s.bind(("", 0))
	try:
		return s.getsockname()[1]
	finally:
		s.close()


def setup_mkcert(cert_dir: Path) -> bool:
	"""Ensure localhost.pem/key exist in cert_dir via mkcert. Return False if
	mkcert is not installed (caller should fall back to caddy internal CA)."""
	if not shutil.which("mkcert"):
		return False
	cert = cert_dir / "localhost.pem"
	key = cert_dir / "localhost-key.pem"
	if cert.is_file() and key.is_file():
		return True
	cert_dir.mkdir(parents=True, exist_ok=True)
	print("dz: first-time mkcert setup", file=sys.stderr)
	if not shutil.which("certutil"):
		print("  NOTE: certutil missing — Firefox won't get the CA.", file=sys.stderr)
		print(f"        apt install libnss3-tools, then rm {cert_dir}/localhost*.pem and rerun", file=sys.stderr)
	subprocess.run(["mkcert", "-install"], check=False)
	subprocess.run(
		["mkcert", "-cert-file", str(cert), "-key-file", str(key), "localhost", "127.0.0.1", "::1"],
		check=True,
	)
	return True


def serve_caddy_docker(tmpdir: Path, srv: Path, dzi: Path, files_dir: Path | None,
					   port: int, prefix_name: str) -> int:
	caddy_dir = tmpdir / "caddy"
	caddy_dir.mkdir(parents=True, exist_ok=True)

	# DZI XML is tiny — copy. _files dir is big — bind-mount.
	shutil.copy2(dzi, srv / dzi.name)
	(srv / f"{prefix_name}_files").mkdir(exist_ok=True)

	cert_dir = CACHE_ROOT / "certs"
	use_mkcert = setup_mkcert(cert_dir)
	tls = ("tls /certs/localhost.pem /certs/localhost-key.pem"
		   if use_mkcert else "tls internal")

	# Tabs-for-indentation matches `caddy fmt`'s expected style, so caddy
	# doesn't emit the "Caddyfile input is not formatted" warning on load.
	(caddy_dir / "Caddyfile").write_text(
		f"{{\n"
		f"\tadmin off\n"
		f"\tauto_https disable_redirects\n"
		f"\tlog default {{\n"
		f"\t\tlevel WARN\n"
		f"\t}}\n"
		f"}}\n"
		f"localhost:{port} {{\n"
		f"\t{tls}\n"
		f"\troot * /srv\n"
		f"\tfile_server\n"
		f"\tencode gzip\n"
		f"\tlog {{\n"
		f"\t\toutput stdout\n"
		f"\t\tformat filter {{\n"
		f"\t\t\twrap console\n"
		f"\t\t\tfields {{\n"
		f"\t\t\t\trequest>headers delete\n"
		f"\t\t\t\trequest>tls delete\n"
		f"\t\t\t\trequest>remote_ip delete\n"
		f"\t\t\t\trequest>remote_port delete\n"
		f"\t\t\t\trequest>host delete\n"
		f"\t\t\t\trequest>proto delete\n"
		f"\t\t\t\tresp_headers delete\n"
		f"\t\t\t\tuser_id delete\n"
		f"\t\t\t\tbytes_read delete\n"
		f"\t\t\t\tduration delete\n"
		f"\t\t\t\tsize delete\n"
		f"\t\t\t}}\n"
		f"\t\t}}\n"
		f"\t}}\n"
		f"}}\n"
	)

	mounts = [
		"-v", f"{srv}:/srv",
		"-v", f"{caddy_dir}:/etc/caddy:ro",
	]
	if use_mkcert:
		mounts += ["-v", f"{cert_dir}:/certs:ro"]
	if files_dir is not None:
		mounts += ["-v", f"{files_dir}:/srv/{prefix_name}_files:ro"]

	cert_kind = "mkcert" if use_mkcert else "internal"
	print(f"serving via caddy (docker, {cert_kind} cert)")
	print()
	print(f"OPEN: https://localhost:{port}/viewer.html")
	if not use_mkcert:
		print("(browser will warn; install mkcert + libnss3-tools for silent operation:")
		print("   sudo apt install mkcert libnss3-tools )")
	print()

	cmd = [
		"docker", "run", "--rm",
		"-p", f"{port}:{port}",
		*mounts,
		"-v", "dz_view_caddy_data:/data",
		"-v", "dz_view_caddy_config:/config",
		"caddy:latest",
	]
	return subprocess.call(cmd)


def serve_python_http(srv: Path, dzi: Path, files_dir: Path | None,
					  port: int, prefix_name: str) -> int:
	(srv / dzi.name).symlink_to(dzi)
	if files_dir is not None:
		(srv / f"{prefix_name}_files").symlink_to(files_dir)
	print("docker not found — falling back to python http.server (HTTP/1.1)")
	print(f"OPEN: http://localhost:{port}/viewer.html")
	print()
	return subprocess.call(
		[sys.executable, "-m", "http.server", str(port)],
		cwd=str(srv),
	)


def cmd_view(args) -> int:
	dzi, files_dir, prefix_name = resolve_pyramid(args.prefix)
	port = args.port or pick_free_port()
	has_docker = shutil.which("docker") is not None

	CACHE_ROOT.mkdir(parents=True, exist_ok=True)
	tmpdir = Path(tempfile.mkdtemp(prefix=f"{prefix_name}.", dir=CACHE_ROOT))
	srv = tmpdir / "srv" if has_docker else tmpdir
	srv.mkdir(parents=True, exist_ok=True)
	try:
		(srv / "viewer.html").write_text(build_viewer_html(prefix_name))
		if has_docker:
			return serve_caddy_docker(tmpdir, srv, dzi, files_dir, port, prefix_name)
		return serve_python_http(srv, dzi, files_dir, port, prefix_name)
	finally:
		shutil.rmtree(tmpdir, ignore_errors=True)


def cmd_deploy(args) -> int:
	dzi, files_dir, prefix_name = resolve_pyramid(args.prefix)

	with tempfile.TemporaryDirectory() as td:
		viewer = Path(td) / "viewer.html"
		viewer.write_text(build_viewer_html(prefix_name))

		cmd = ["rsync", "-avP"]
		if args.dry_run:
			cmd.append("-n")
		cmd.append(str(dzi))
		if files_dir is not None:
			cmd.append(str(files_dir))
		cmd += [str(viewer), args.remote]

		print("$ " + " ".join(cmd), file=sys.stderr)
		return subprocess.call(cmd)


def main() -> int:
	# Line-buffer stdout regardless of TTY/pipe so the "OPEN: https://..." line
	# shows up before caddy's log spam even when output is redirected.
	sys.stdout.reconfigure(line_buffering=True)

	ap = argparse.ArgumentParser(
		description=__doc__,
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	sub = ap.add_subparsers(dest="cmd", required=True)

	p_view = sub.add_parser("view", help="serve locally (caddy+docker, or python fallback)")
	p_view.add_argument("prefix", help="pyramid prefix (with or without .dzi)")
	p_view.add_argument("--port", type=int, default=None,
						help="port; default: auto-pick a free ephemeral port")
	p_view.set_defaults(fn=cmd_view)

	p_deploy = sub.add_parser("deploy", help="rsync pyramid + viewer.html to a remote web server")
	p_deploy.add_argument("prefix", help="pyramid prefix (with or without .dzi)")
	p_deploy.add_argument("remote", help="rsync target, e.g. user@host:/var/www/html/pano/")
	p_deploy.add_argument("-n", "--dry-run", action="store_true",
						  help="pass -n to rsync (no transfer)")
	p_deploy.set_defaults(fn=cmd_deploy)

	args = ap.parse_args()
	return args.fn(args) or 0


if __name__ == "__main__":
	sys.exit(main())
