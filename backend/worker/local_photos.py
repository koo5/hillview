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

# Total symlink expansions across ALL path components (the walk covers
# intermediate DIRECTORY links too — the pipeline's offdisk spill makes e.g.
# ``.../misc/phase_tiff -> /var/data/tiff/home/...``, HV_OFFDISK_ROOT).
# Counted in the real layouts: spilled phase dir = 1 hop; a sorted/-style file
# link whose target then crosses a spilled dir = 2. Known-max + 1; deeper
# chains are a config smell.
MAX_SYMLINK_HOPS = 3


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
	readable regular file), walking symlinks at EVERY component with per-hop
	containment.

	The walk descends from a configured root one component at a time through
	the container mount. A symlink at any component — an offdisk-spilled
	directory (``phase_tiff -> /var/data/tiff/home/...``) as much as a final
	marker link — is expanded by splicing its target (resolved against the
	link's HOST directory when relative) with the remaining components, and
	the containment check restarts from the top: a target may land in a
	different root, and every hop must map into some configured root. So
	"target outside the photo roots" and "target's tree not mounted here"
	each fail with a message naming the offending hop rather than a generic
	error, and no path the kernel would traverse is ever taken on trust.
	"""
	table = roots()
	path = host_path
	hops = 0
	while True:
		name, cpath = host_to_container(path, table)
		croot = container_root(name)
		rel = os.path.relpath(cpath, croot)
		comps = [] if rel == "." else rel.split(os.sep)
		cur_host, cur_cont = table[name], croot
		spliced = False
		for i, comp in enumerate(comps):
			cur_host = os.path.join(cur_host, comp)
			cur_cont = os.path.join(cur_cont, comp)
			if os.path.islink(cur_cont):
				hops += 1
				if hops > MAX_SYMLINK_HOPS:
					raise LocalPhotoPathError(
						f"too many symlink hops resolving {host_path!r} (limit {MAX_SYMLINK_HOPS})")
				target = os.readlink(cur_cont)
				if not os.path.isabs(target):
					target = os.path.join(os.path.dirname(cur_host), target)
				path = os.path.join(target, *comps[i + 1:])  # host space; re-checked from the top
				spliced = True
				break
		if spliced:
			continue
		if not os.path.exists(cur_cont):
			raise LocalPhotoPathError(
				f"path {path!r} does not exist in the worker container as {cur_cont!r} (is its tree mounted?)")
		if not os.path.isfile(cur_cont):
			raise LocalPhotoPathError(f"path {path!r} is not a regular file")
		if not os.access(cur_cont, os.R_OK):
			raise LocalPhotoPathError(f"path {path!r} is not readable by the worker")
		# Belt and braces: the walk expanded every link it saw, so by
		# construction nothing here should re-resolve elsewhere — but if a
		# link appears mid-walk (a race with the pipeline re-spilling a dir),
		# the kernel would follow it on open, so assert the container-space
		# resolution still lands under EXTERNAL_DATA_DIR.
		real = os.path.realpath(cur_cont)
		if not _under(real, EXTERNAL_DATA_DIR):
			raise LocalPhotoPathError(
				f"path {path!r} resolves outside {EXTERNAL_DATA_DIR} in the container ({real!r}) — a symlink escapes the mounted roots")
		return name, cur_cont


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
