"""Client-named local photo trees (no-upload ingestion, external pyramid offers).

The client — the pipeline's upload CLI — names files by their HOST path
(``/home/koom/autocopy/...``). The worker never mounts host trees at their
host paths; each configured root is bind-mounted read-only under one fixed,
generic prefix:

    LOCAL_PHOTO_ROOTS = "autocopy=/home/koom/autocopy;tiff=/var/data/tiff"
    container mounts:    /external-data/autocopy, /external-data/tiff

so every path the worker touches is CONSTRUCTED as
``EXTERNAL_DATA_DIR/<root name>/<path relative to that root>`` — a client
cannot aim at anything outside EXTERNAL_DATA_DIR by any spelling, because
container paths are never taken from the client at all. Containment is a
prefix test in host space against the configured roots only; the same test
is applied to every symlink hop (targets in the archive are absolute host
paths like ``/var/data/tiff/...``, so they must be re-mapped through the same
table). This is what makes the anti-hijack property easy to state and easy to
audit.

Env is read at call time so the pool subprocess (photo_processor) needs no
extra plumbing.
"""

import os
from typing import Dict, Optional, Tuple

EXTERNAL_DATA_DIR = "/external-data"

MAX_SYMLINK_HOPS = 2  # a marker link → the artifact, at most; deeper chains are a config smell


class LocalPhotoPathError(ValueError):
	"""The client-supplied path cannot be resolved to a readable file inside a
	configured root. The message names the offending hop / reason."""


def roots() -> Dict[str, str]:
	"""root name → host root path, from LOCAL_PHOTO_ROOTS ("name=hostpath;...").
	Empty when the feature is off on this worker."""
	out: Dict[str, str] = {}
	for pair in os.getenv("LOCAL_PHOTO_ROOTS", "").split(";"):
		if "=" in pair:
			name, host = pair.split("=", 1)
			name, host = name.strip(), os.path.normpath(host.strip())
			if name and os.path.isabs(host):
				out[name] = host
	return out


def container_root(name: str) -> str:
	return os.path.join(EXTERNAL_DATA_DIR, name)


def _under(path: str, root: str) -> bool:
	return path == root or path.startswith(root.rstrip("/") + "/")


def host_to_container(host_path: str, table: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
	"""Map an absolute host path to (root name, container path), or raise
	LocalPhotoPathError if it is under no configured root."""
	table = roots() if table is None else table
	if not table:
		raise LocalPhotoPathError("this worker has no LOCAL_PHOTO_ROOTS configured")
	if not os.path.isabs(host_path):
		raise LocalPhotoPathError(f"path must be absolute: {host_path!r}")
	host_path = os.path.normpath(host_path)  # collapses any '..' — a path that escapes a root simply won't be under one
	for name, host_root in sorted(table.items(), key=lambda kv: len(kv[1]), reverse=True):
		if _under(host_path, host_root):
			rel = os.path.relpath(host_path, host_root)
			cpath = os.path.normpath(os.path.join(container_root(name), rel))
			assert _under(cpath, EXTERNAL_DATA_DIR), cpath  # by construction; belt and braces
			return name, cpath
	raise LocalPhotoPathError(f"path {host_path!r} is outside LOCAL_PHOTO_ROOTS {sorted(table.values())}")


def resolve_local_photo_path(host_path: str) -> Tuple[str, str]:
	"""Resolve a client-supplied HOST path to (root name, container path of a
	readable regular file), walking symlinks manually with per-hop containment.

	Each hop — the path itself and every link target — must map into a
	configured root and exist in the container, so "target outside the photo
	roots" and "target's tree not mounted here" each fail with a message
	naming the offending hop rather than a generic error. Directory symlinks
	along the way are not walked (the roots are operator-mounted trees and the
	uploader is authenticated; this is a dev-box feature, not a sandbox).
	"""
	table = roots()
	path = host_path
	for _hop in range(MAX_SYMLINK_HOPS + 1):
		name, cpath = host_to_container(path, table)
		if os.path.islink(cpath):
			target = os.readlink(cpath)
			if not os.path.isabs(target):
				target = os.path.join(os.path.dirname(os.path.normpath(path)), target)
			path = target  # stays in host space; containment re-checked next hop
			continue
		if not os.path.exists(cpath):
			raise LocalPhotoPathError(
				f"path {path!r} does not exist in the worker container as {cpath!r} (is its tree mounted?)")
		if not os.path.isfile(cpath):
			raise LocalPhotoPathError(f"path {path!r} is not a regular file")
		if not os.access(cpath, os.R_OK):
			raise LocalPhotoPathError(f"path {path!r} is not readable by the worker")
		return name, cpath
	raise LocalPhotoPathError(f"too many symlink hops resolving {host_path!r} (limit {MAX_SYMLINK_HOPS})")


def root_name_of(cpath: str) -> str:
	"""Root name of a container path produced by this module
	(``EXTERNAL_DATA_DIR/<name>/...``)."""
	rel = os.path.relpath(os.path.normpath(cpath), EXTERNAL_DATA_DIR)
	if rel.startswith(".."):
		raise LocalPhotoPathError(f"{cpath!r} is not under {EXTERNAL_DATA_DIR}")
	return rel.split(os.sep, 1)[0]


def url_for(cpath: str) -> Optional[str]:
	"""Public URL of a container path under one of the roots, from
	LOCAL_PHOTO_URLS ("name=url;..." — where Caddy serves that root), or None
	if that root is unmapped."""
	name = root_name_of(cpath)
	urls = dict(pair.split("=", 1) for pair in os.getenv("LOCAL_PHOTO_URLS", "").split(";") if "=" in pair)
	base = urls.get(name)
	if not base:
		return None
	return base.rstrip("/") + "/" + os.path.relpath(cpath, container_root(name))
