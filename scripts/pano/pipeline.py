#!/usr/bin/env python3
"""
End-to-end SDR panorama pipeline: CR2 -> rendered EXR + DZI pyramid.

Runs each step as a numbered phase with its own output directory. Phases
are resumable and idempotent:

	- If phase_NN_name/ exists, the phase is skipped.
	- Each phase works in phase_NN_name.tmp/ and atomically renames on success.
	- Ctrl-C leaves the .tmp/ behind for inspection; next run refuses to
		touch it until you explicitly `mv` it to accept or `rm -rf` to retry.

Phase order is the PHASES list below. Numbers are auto-assigned from list
position, so reordering / inserting / removing phases just edits the list.
Phase short names:
	tiff      darktable-developed TIFFs
	fused     exposure-fused TIFFs (reflink-copied from tiff if brackets==1)
	pto       pto_gen + cpfind --linearmatch --celeste
	topmost   pto_cp_topmost --per-side K
	baseline  pto_horizontal_baseline --overlap N
	optimize  pto_optvars + autooptimiser (y -> y,p -> y,p,r)
	stitch    pto_stitch_exr -> linearized EXR (hillview:encoding=linear)
	render    darktable-cli applies an XMP -> display-referred EXR
	          (hillview:encoding=srgb)
	pyramid   exr_to_webp_pyramid -> DZI tile pyramid

Usage:
	pipeline.py --raws-dir R --overlap PCT
							[--work-dir W]  (default: <raws-dir>/<first>---<last>/)
							[--brackets-per-stack N] [--topmost-per-side K]
							[--celeste-threshold T] [--jobs N]
							[--stop-after SHORT_NAME]
							[--redo SHORT_NAME_OR_NUM]

The render phase needs an XMP sidecar to drive darktable. On first run
the pipeline copies scripts/pano/default_pano.xmp into <work-dir>/render/
as <derived>.exr.xmp. To tweak it: open <work-dir>/render/<derived>.exr
in the darktable GUI (the XMP next to it is auto-loaded), make changes,
save, then `rm -rf <work-dir>/phase_08_render` and rerun. The XMP
persists across phase rebuilds — including phase_07_stitch — so you can
re-stitch without losing rendering tweaks.

The final EXR is named <first_stem>---<last_stem>.exr inside
phase_NN_render/. The DZI pyramid lands in phase_NN_pyramid/.
"""

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DARKTABLE = SCRIPT_DIR.parent / "raw" / "raw_darktable.py"
ENFUSE_BRACKET = SCRIPT_DIR / "enfuse_bracket.sh"
BASELINE = SCRIPT_DIR / "pto_horizontal_baseline.py"
TOPMOST = SCRIPT_DIR / "pto_cp_topmost.py"
OPTVARS = SCRIPT_DIR / "pto_optvars.py"
STITCH = SCRIPT_DIR / "pto_stitch_exr.py"
LINEARIZE = SCRIPT_DIR / "exr_linearize.py"
EXR_META = SCRIPT_DIR / "exr_meta.py"
EXR_TO_PYRAMID = SCRIPT_DIR / "exr_to_webp_pyramid.py"
EXR_SANITY = SCRIPT_DIR / "exr_sanity.sh"
XMP_MODULE = SCRIPT_DIR / "xmp_module.py"
DARKTABLE_CLI = SCRIPT_DIR.parent / "raw" / "darktable-cli-flatpak.sh"
DEFAULT_XMP = SCRIPT_DIR / "default_pano.xmp"


def run(cmd: list) -> None:
		cmd = [str(c) for c in cmd]
		print(f"$ {' '.join(shlex.quote(c) for c in cmd)}",
					file=sys.stderr, flush=True)
		subprocess.run(cmd, check=True)


def reflink_cp(src: Path, dst: Path) -> None:
		run(["cp", "--reflink=auto", src, dst])


@dataclass
class Phase:
		short: str
		body: Callable[[Path, Optional[Path]], None]  # (staging, prev_phase_dir)


def run_phase(name: str, work_dir: Path, body: Callable[[Path], None]) -> Path:
		final = work_dir / name
		staging = work_dir / f"{name}.tmp"

		if final.exists():
				print(f"[{name}] skipped (already at {final.name}/)", file=sys.stderr)
				return final

		if staging.exists():
				print(f"\n[{name}] staging {staging.name}/ exists from a previous run.",
							file=sys.stderr)
				print(f"  inspect: ls {staging.name}/", file=sys.stderr)
				print(f"  accept:  mv {staging.name} {final.name}", file=sys.stderr)
				print(f"  retry:   rm -rf {staging.name}", file=sys.stderr)
				sys.exit(3)

		print(f"\n[{name}] starting in {staging.name}/", file=sys.stderr)
		staging.mkdir(parents=True)
		try:
				body(staging)
		except (subprocess.CalledProcessError, KeyboardInterrupt):
				print(f"\n[{name}] FAILED — staging preserved at {staging.name}/",
							file=sys.stderr)
				raise
		except Exception:
				print(f"\n[{name}] ERROR — staging preserved at {staging.name}/",
							file=sys.stderr)
				raise

		staging.rename(final)
		print(f"[{name}] committed to {final.name}/", file=sys.stderr)
		return final


def main() -> int:
		ap = argparse.ArgumentParser(
				description=__doc__,
				formatter_class=argparse.RawDescriptionHelpFormatter,
		)
		ap.add_argument("--work-dir", type=Path, default=None,
										help="Where phase_NN_* directories are created. "
												 "Defaults to <raws-dir>/<first_stem>---<last_stem>/.")
		ap.add_argument("--raws-dir", type=Path, required=True,
										help="Directory containing the .CR2 (or .cr2) files.")
		ap.add_argument("--brackets-per-stack", type=int, default=1,
										help="1 (default, no fusing) or 3/5/7 for AEB. Files "
												 "grouped in filename-sorted order.")
		ap.add_argument("--overlap", type=float, required=True,
										help="Horizontal overlap percent between adjacent frames.")
		ap.add_argument("--topmost-per-side", type=int, default=2,
										help="Topmost filter: CPs per (image, L/R). Default 2.")
		ap.add_argument("--celeste-threshold", type=float, default=0.5,
										help="cpfind --celeste threshold. Default 0.5.")
		ap.add_argument("--jobs", type=int, default=4,
										help="Parallel workers for raw_darktable.")
		ap.add_argument("--stop-after", default=None,
										help="Stop after this phase short name (e.g. baseline).")
		ap.add_argument("--redo", default=None,
										help="Discard committed and staging output of this phase "
												 "and every later phase, then rerun from there. "
												 "Accepts a phase short name (e.g. 'render') or "
												 "1-based number ('8'). Equivalent to manual "
												 "`rm -rf phase_NN_<short>{,.tmp}` for those phases.")
		args = ap.parse_args()

		raws_dir = args.raws_dir.resolve()
		if not raws_dir.is_dir():
				print(f"error: --raws-dir not a directory: {raws_dir}", file=sys.stderr)
				return 2
		cr2s = sorted(list(raws_dir.glob("*.CR2")) + list(raws_dir.glob("*.cr2")))
		if not cr2s:
				print(f"error: no CR2 files in {raws_dir}", file=sys.stderr)
				return 2

		# Derived name from first..last raw stems. Used as default work-dir
		# name and as the final EXR filename.
		derived_name = f"{cr2s[0].stem}---{cr2s[-1].stem}"

		work_dir = args.work_dir.resolve() if args.work_dir else (raws_dir / derived_name)
		work_dir.mkdir(parents=True, exist_ok=True)
		print(f"work dir: {work_dir}", file=sys.stderr)
		print(f"output:   {derived_name}.exr", file=sys.stderr)

		def _tiff(staging: Path, prev: Optional[Path]) -> None:
				run([RAW_DARKTABLE, raws_dir, "-o", staging, "-j", args.jobs])

		def _fused(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				tiffs = sorted(prev.glob("*.tif"))
				if not tiffs:
						raise RuntimeError(f"no TIFFs in {prev}")
				if args.brackets_per_stack == 1:
						for t in tiffs:
								reflink_cp(t, staging / t.name)
						return
				bps = args.brackets_per_stack
				if len(tiffs) % bps != 0:
						print(f"warning: {len(tiffs)} TIFFs is not a multiple of "
									f"brackets_per_stack={bps}; trailing {len(tiffs) % bps} "
									f"skipped", file=sys.stderr)
				for i in range(0, len(tiffs) - bps + 1, bps):
						stack = tiffs[i:i + bps]
						fused = staging / f"fused_{i // bps:04d}.tif"
						run([ENFUSE_BRACKET, fused, *stack])

		def _pto(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				tiffs = sorted(prev.glob("*.tif"))
				pto = staging / "pano.pto"
				run(["pto_gen", "-o", pto, *tiffs])
				run([
						"cpfind",
						"--linearmatch",
						"--celeste",
						f"--celestethreshold={args.celeste_threshold}",
						"-o", pto, pto,
				])
				# cpfind can exit 0 despite rejecting unknown flags, leaving a PTO
				# with zero CPs. Catch that here so downstream phases don't quietly
				# operate on an empty graph.
				n_cps = sum(1 for ln in pto.read_text().splitlines() if ln.startswith("c "))
				if n_cps == 0:
						raise RuntimeError(
								f"cpfind produced 0 CPs — check cpfind flags or whether "
								f"adjacent images have usable overlap (fused TIFFs in {prev})"
						)
				print(f"cpfind: {n_cps} CPs total", file=sys.stderr)

		def _topmost(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				run([
						TOPMOST, prev / "pano.pto",
						"--per-side", str(args.topmost_per_side),
						"-o", staging / "pano.pto",
				])

		def _baseline(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				run([
						BASELINE, prev / "pano.pto",
						"--overlap", str(args.overlap),
						"-o", staging / "pano.pto",
				])

		def _optimize(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				dst = staging / "pano.pto"
				reflink_cp(prev / "pano.pto", dst)
				for free in ("y", "y,p", "y,p,r"):
						run([OPTVARS, dst, "--free", free, "--in-place"])
						# autooptimiser needs distinct input and output paths.
						tmp = staging / "pano.opt.pto"
						run(["autooptimiser", "-n", dst, "-o", tmp])
						tmp.replace(dst)

		def _stitch(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				dst_pto = staging / "pano.pto"
				# pto_gen defaults to a tiny w3000 h1500 v360 canvas, which renders
				# the pano as ~1200 px wide regardless of source resolution.
				# --straighten:  level the horizon (minimize mean pitch drift)
				# --fov=AUTO:    shrink output FOV to match actual image coverage
				# --canvas=AUTO: size canvas in pixels to match source density
				# --crop=AUTO:   trim the rendered bounding box to content
				run([
						"pano_modify",
						"--straighten",
						"--fov=AUTO", "--canvas=AUTO", "--crop=AUTO",
						"-o", dst_pto, prev / "pano.pto",
				])
				# pto_stitch_exr chdirs to the pto's parent, so warp layers & final
				# EXR both land in staging/. --no-tag skips the default
				# hillview:encoding=srgb write — we're about to linearize and retag.
				run([STITCH, dst_pto, "--prefix", "pano", "--no-tag"])
				# Rename the final EXR to <first>---<last>.exr so multiple panos
				# in the same parent dir don't overwrite each other when you move
				# files around. Warp layers stay as pano0000.tif etc. — they're
				# internal and get rm'd later anyway.
				(staging / "pano.exr").rename(staging / f"{derived_name}.exr")
				# Apply inverse sRGB OETF so the EXR's pixel values are genuinely
				# scene-linear, matching the industry EXR convention. Tools that
				# assume EXR=linear (darktable, Nuke) then render correctly. Tag
				# becomes hillview:encoding=linear.
				run([LINEARIZE, staging / f"{derived_name}.exr"])

		# Persistent darktable workspace: lives at <work_dir>/render/, outside
		# any phase. Holds the editable XMP plus a reflink to the linearized
		# EXR. Survives `rm -rf phase_07_stitch` and `rm -rf phase_08_render`,
		# so users can re-stitch and re-render without losing tweaks.
		render_ws = work_dir / "render"
		ws_exr = render_ws / f"{derived_name}.exr"
		ws_xmp = render_ws / f"{derived_name}.exr.xmp"

		def _ensure_render_workspace(source_exr: Path) -> None:
				render_ws.mkdir(parents=True, exist_ok=True)
				# Always refresh the EXR reflink — phase_07 may have been re-run
				# with new pixels and the workspace handle would otherwise be
				# stale. cp --reflink=auto overwrites; cheap on cow filesystems.
				if ws_exr.exists():
						ws_exr.unlink()
				reflink_cp(source_exr, ws_exr)
				# Never overwrite an existing XMP: that's the user's tweaked
				# render recipe. First run gets the default; subsequent runs
				# preserve whatever darktable last wrote.
				if not ws_xmp.exists():
						print(f"  no existing XMP — copying {DEFAULT_XMP.name}",
									file=sys.stderr)
						reflink_cp(DEFAULT_XMP, ws_xmp)
				else:
						print(f"  reusing existing XMP at {ws_xmp}",
									file=sys.stderr)

		def _render(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				_ensure_render_workspace(prev / f"{derived_name}.exr")
				# Surface which modules are about to run. Helps catch
				# known-problematic ones before burning CPU-minutes:
				# bilat / shadhi crash on gigapixel inputs; denoiseprofile
				# eats tens of GB of RAM. Doesn't gate the render — just
				# prints, so the user can ctrl-C if something looks wrong.
				print(f"\n[render] modules enabled in {ws_xmp.name}:",
							file=sys.stderr)
				out = subprocess.run(
						[str(XMP_MODULE), "list", str(render_ws),
						 "--pattern", ws_xmp.name],
						capture_output=True, text=True, check=True,
				).stdout
				for line in out.splitlines():
						if "enabled=1" in line:
								print(f"  {line.strip()}", file=sys.stderr)
				out_exr = staging / f"{derived_name}.exr"
				# bpp=16: half-float is enough range for display-referred
				# [0, 1] output and halves the file size vs 32-bit float.
				# resourcelevel=large: lets darktable use a larger memory
				# budget on the 24-core / 128 GB box. Note: certain darktable
				# modules (bilat, shadhi) crash on gigapixel inputs regardless
				# of resource level — disable them in the XMP, don't expect
				# them to work here.
				run([
						DARKTABLE_CLI, ws_exr, ws_xmp, out_exr,
						"--core",
						"--conf", "resourcelevel=large",
						"--conf", "plugins/imageio/format/exr/bpp=16",
				])
				# darktable's gamma module applied the sRGB OETF on export, so
				# the pixels are display-referred. Tag accordingly so the
				# Hillview worker doesn't re-apply OETF on ingest.
				run([EXR_META, "set", out_exr, "--encoding", "srgb"])

		def _pyramid(staging: Path, prev: Optional[Path]) -> None:
				assert prev is not None
				src_exr = prev / f"{derived_name}.exr"
				# exr_to_webp_pyramid reads hillview:encoding off the input;
				# it'll error if the tag is missing or unknown. Output:
				# <prefix>.dzi + <prefix>_files/.
				run([
						EXR_TO_PYRAMID, src_exr,
						staging / derived_name,
				])

		PHASES = [
				Phase("tiff",     _tiff),
				Phase("fused",    _fused),
				Phase("pto",      _pto),
				Phase("topmost",  _topmost),
				Phase("baseline", _baseline),
				Phase("optimize", _optimize),
				Phase("stitch",   _stitch),
				Phase("render",   _render),
				Phase("pyramid",  _pyramid),
		]

		shorts = [p.short for p in PHASES]
		if args.stop_after is not None and args.stop_after not in shorts:
				print(f"error: --stop-after '{args.stop_after}' not in {shorts}",
							file=sys.stderr)
				return 2

		# Resolve --redo to a phase index, then discard the committed and
		# staging output of every phase from that index to the end. The
		# main loop handles re-running them on its normal pass.
		if args.redo is not None:
				if args.redo.isdigit():
						n = int(args.redo)
						if not 1 <= n <= len(PHASES):
								print(f"error: --redo {n} out of range [1, {len(PHASES)}]",
											file=sys.stderr)
								return 2
						redo_idx = n - 1
				elif args.redo in shorts:
						redo_idx = shorts.index(args.redo)
				else:
						print(f"error: --redo '{args.redo}' not in {shorts} "
									f"and not a 1-based number in [1, {len(PHASES)}]",
									file=sys.stderr)
						return 2
				for i in range(redo_idx, len(PHASES)):
						short = PHASES[i].short
						for suffix in ("", ".tmp"):
								target = work_dir / f"phase_{i + 1:02d}_{short}{suffix}"
								if target.exists():
										print(f"--redo: removing {target.name}/", file=sys.stderr)
										shutil.rmtree(target)

		prev: Optional[Path] = None
		last_short: Optional[str] = None
		for i, phase in enumerate(PHASES, start=1):
				full_name = f"phase_{i:02d}_{phase.short}"
				# Capture phase + prev in default args to avoid late-binding over the loop.
				body_closure = lambda staging, p=phase, prev_path=prev: p.body(staging, prev_path)
				committed = run_phase(full_name, work_dir, body_closure)
				prev = committed
				last_short = phase.short
				if args.stop_after == phase.short:
						print(f"\nstopping after '{phase.short}' as requested.",
									file=sys.stderr)
						return 0

		# Tail message picks the most useful artifact path for whatever the
		# last completed phase was, plus copy-paste diagnostics for the
		# EXRs that exist. exr_sanity.sh prints encoding tag + pixel range
		# + a tag-vs-range consistency verdict.
		stitch_exr = work_dir / "phase_07_stitch" / f"{derived_name}.exr"
		render_exr = work_dir / "phase_08_render" / f"{derived_name}.exr"

		if last_short == "pyramid":
				dzi_prefix = prev / derived_name
				print(f"\ndone. pyramid: {dzi_prefix}.dzi", file=sys.stderr)
				print(f"  view:  {SCRIPT_DIR / 'dz.py'} view {dzi_prefix}",
							file=sys.stderr)
		elif last_short == "render":
				print(f"\ndone. rendered EXR: {render_exr}", file=sys.stderr)
		else:
				print(f"\ndone. final: {prev / f'{derived_name}.exr'}", file=sys.stderr)

		print("\ndiagnostics:", file=sys.stderr)
		if stitch_exr.exists():
				print(f"  {EXR_SANITY} {stitch_exr}", file=sys.stderr)
		if render_exr.exists():
				print(f"  {EXR_SANITY} {render_exr}", file=sys.stderr)
		return 0


if __name__ == "__main__":
		try:
				sys.exit(main())
		except KeyboardInterrupt:
				sys.exit(130)
