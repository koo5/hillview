#!/usr/bin/env python3
"""
CR2 raw photo processing pipeline.

Converts CR2 files in the current directory through:
	CR2 -> TIFF (via RawTherapee) -> WebP (via cwebp)

Then copies EXIF tags and geotags the WebP files.

Run from a directory containing *.CR2 files.
"""
##!/usr/bin/env fish

import argparse
import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
from lib.brackets import print_groups  # noqa: E402

DARKTABLE_WRAPPER = SCRIPT_DIR / "darktable-cli-flatpak.sh"
DEFAULT_STACK_XMP = SCRIPT_DIR / "default_stack.xmp"
MAX_WORKERS = 10
RAWTHERAPEE_PROFILES = [
		"/usr/share/rawtherapee/profiles/Auto-Matched Curve - ISO Low.pp3",
#    str(Path(__file__).resolve().parent / "vivid.pp3"),
]
CWEBP_ARGS = ["-preset", "photo", "-q", "98"]
# Disabled cwebp args, kept for future reference:
# "-m", "6", "-af", "-metadata", "all"

def log(msg):
		print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

#set DIR (dirname (readlink -m (status --current-filename)))
#mkdir tiff; mkdir webp; mkdir webp_noanon;
def setup_dirs():
		# aligned/ + enfused/ are the bracket-fusion intermediates kept on disk
		# so each step is debuggable: aligned/<stem>_NNNN.tif from
		# align_image_stack, enfused/<stem>.tif from enfuse, tiff/<stem>_fused.tiff
		# from darktable applying default_stack.xmp.
		for d in ["tiff", "webp", "webp_noanon", "aligned", "enfused"]:
				Path(d).mkdir(exist_ok=True)

def convert_all_cr2_to_tiff(tiff_dir):
	with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
		for f in sorted(Path(".").glob("*.CR2")):
			# skip if the tiff already exists
			stem = f.stem
			if (tiff_dir / f"{stem}.tif").exists() or (tiff_dir / f"{stem}.tiff").exists():
					continue
			pool.submit(cr2_to_tiff, f, tiff_dir)
def cr2_to_tiff(f, tiff_dir):
		log(f"Converting {f.name} -> TIFF")
		profile_args = [arg for p in RAWTHERAPEE_PROFILES for arg in ("-p", p)]
		# -b16: 16-bit per channel. Was -b8 historically (smaller files), but
		# anything downstream that does HDR/focus fusion on a bracket stack
		# starts with 8 bits of data per pixel and has zero highlight/shadow
		# headroom — half the point of bracketing in the first place. cwebp
		# at the end of the chain downsamples to 8-bit regardless, so the
		# only cost here is on-disk TIFF size (~2× per file).
		subprocess.run([
				"rawtherapee-cli",
				*profile_args,
				"-o", str(tiff_dir / f"{f.stem}.tiff"),
				"-tz", "-b16",
				"-c", str(f),
		])
def copy_cr2_tags_to_tiffs(tiff_dir):
		"""Copy lens/camera EXIF tags from CR2 to TIFF for Hugin compatibility."""
		with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
				for cr2 in sorted(Path(".").glob("*.CR2")):
						tiff_path = find_tiff(tiff_dir, cr2.stem)
						pool.submit(copy_cr2_tags_to_tiff, cr2, tiff_path)

def copy_cr2_tags_to_tiff(cr2, tiff_path):
		log(f"Copying EXIF tags {cr2.name} -> {tiff_path.name}")
		# Orientation is intentionally NOT in the copy list. RawTherapee (with
		# our profile + cli flags) emits pixels rotated 180° from upright for
		# every shot regardless of the CR2's Orientation tag, and tags its TIFF
		# output Orientation=3 to compensate. Pulling Orientation from the CR2
		# here would clobber that =3 with 1/6/8 and break display.
		subprocess.run([
				"exiftool", "-overwrite_original",
				"-TagsFromFile", str(cr2),
				"-Make", "-Model", "-LensModel", "-FocalLength", "-FocalLengthIn35mmFilm",
				"-DateTimeOriginal",
				str(tiff_path),
		], check=True)

def find_tiff(tiff_dir, stem):
		"""Find a .tif or .tiff file for the given stem (rawtherapee may produce either)."""
		for ext in (".tiff", ".tif"):
				p = tiff_dir / f"{stem}{ext}"
				if p.exists():
						return p
		raise FileNotFoundError(f"No .tif or .tiff found for {stem} in {tiff_dir}")

# profile was: -preset photo -q 98  # -m 6 -af -metadata all
def convert_all_tiff_to_webp(tiff_dir, webp_dir):
	with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
		for f in sorted(Path(".").glob("*.CR2")):
			stem = f.stem
			if (webp_dir / f"{stem}.webp").exists():
					continue
			pool.submit(tiff_to_webp, find_tiff(tiff_dir, stem), webp_dir)

def tiff_to_webp(tiff_path, webp_dir):
		stem = tiff_path.stem
		log(f"Converting {tiff_path.name} -> WebP")
		subprocess.run([
				"cwebp", *CWEBP_ARGS,
				str(tiff_path),
				"-o", str(webp_dir / f"{stem}.webp"),
		])

def copy_exif():
		subprocess.run([str(SCRIPT_DIR / "exif_tags_from_cr2_to_webp.sh")], check=True)


def fuse_brackets(tiff_dir, webp_dir, aligned_dir, enfused_dir):
		"""Detect AEB stacks among the CR2s and produce <middle>_fused.{tiff,webp}.

		Three-stage fusion, each stage's output kept on disk for review:
		  1. align_image_stack  -> aligned/<stem>_NNNN.tif
		  2. enfuse             -> enfused/<stem>.tif         (focus-fusion
		     flags: --hard-mask + contrast-only weighting)
		  3. darktable applies  -> tiff/<stem>_fused.tiff      (per-stack
		     enfused/<stem>.tif.xmp, copied from default_stack.xmp on first
		     run so the user can tweak each stack individually in darktable
		     and re-run)

		Per-frame TIFFs and webps are kept regardless — the user reviews after
		processing and decides which to keep. Singletons are skipped.

		Hard-fails if scripts/raw/default_stack.xmp is missing — that file is
		the seed for every per-stack XMP and there's no sensible fallback.
		"""
		cr2s = sorted(Path(".").glob("*.CR2"))
		groups = print_groups(cr2s)
		bracketed = [g for g in groups if len(g) >= 2]
		if not bracketed:
				log("No bracket stacks detected; skipping fuse phase")
				return
		if not DEFAULT_STACK_XMP.exists():
				raise FileNotFoundError(
						f"{DEFAULT_STACK_XMP} not found — required to seed per-stack "
						f"XMPs for the darktable finalize step. Create the default XMP "
						f"(e.g. by editing one CR2 in darktable, exporting its sidecar, "
						f"and saving to that path) and re-run."
				)

		with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
				for group in bracketed:
						pool.submit(_fuse_one_group, group, tiff_dir, webp_dir,
						            aligned_dir, enfused_dir)


def _align_stack(group, tiff_dir, aligned_dir, stem):
		"""align_image_stack on group's per-frame TIFFs -> aligned/<stem>_NNNN.tif.
		Idempotent: skips if all expected outputs exist.
		"""
		expected = [aligned_dir / f"{stem}_{i:04d}.tif" for i in range(len(group))]
		if all(p.exists() for p in expected):
				return expected
		try:
				tiff_inputs = [str(find_tiff(tiff_dir, c.stem)) for c in group]
		except FileNotFoundError as e:
				log(f"skip align {stem}: {e}")
				return None
		log(f"Aligning {len(group)} frames -> aligned/{stem}_*")
		# -t 1: tighter CP reprojection threshold (default 3px). Moving objects
		# (cars, pedestrians) within a stack produce CPs that agree across frames
		# but disagree with the stationary majority; the tighter threshold drops
		# them before they pull the solve sideways. Same flag the pano pipeline
		# uses in enfuse_bracket.sh.
		subprocess.run([
				"align_image_stack", "-t", "1",
				"-a", str(aligned_dir / f"{stem}_"),
				*tiff_inputs,
		], check=True)
		return sorted(aligned_dir.glob(f"{stem}_*.tif"))


def _enfuse_stack(aligned_paths, enfused_dir, stem):
		"""enfuse aligned frames -> enfused/<stem>.tif. Idempotent.

		Focus-stacking flags: --hard-mask + contrast-only weighting, with
		exposure/saturation/entropy disabled. The fusion picks the sharpest
		pixel per location rather than blending exposures. (For exposure
		fusion, drop --hard-mask and use exposure/saturation weights.)
		"""
		out = enfused_dir / f"{stem}.tif"
		if out.exists():
				return out
		log(f"Enfusing -> {out.name}")
		subprocess.run([
				"enfuse", "-v",
				"--hard-mask",
				"--contrast-weight=1",
				"--saturation-weight=0",
				"--exposure-weight=0",
				"--entropy-weight=0",
				f"--output={out}",
				*map(str, aligned_paths),
		], check=True)
		return out


def _darktable_finalize(enfused_path, fused_tiff, middle_cr2):
		"""Apply per-stack XMP via darktable: enfused -> fused_tiff. Idempotent.

		Per-stack workflow:
		  - On first run, copies DEFAULT_STACK_XMP to enfused/<stem>.tif.xmp.
		  - Subsequent runs reuse whatever's at enfused/<stem>.tif.xmp, so the
		    user can open enfused/<stem>.tif in the darktable GUI, tweak,
		    save (which writes the XMP), then `rm tiff/<stem>_fused.tiff` and
		    re-run raw.sh to apply the tweaks.
		"""
		if fused_tiff.exists():
				return
		# Camera EXIF needs to be on the enfused TIFF before darktable consumes
		# it — darktable derives FocalLength/FocalPlane*/etc. from input EXIF,
		# and enfuse strips everything. Pull from the middle bracket.
		subprocess.run([
				"exiftool", "-overwrite_original",
				"-TagsFromFile", str(middle_cr2),
				"-Make", "-Model", "-LensModel", "-LensInfo",
				"-FocalLength", "-FocalLengthIn35mmFilm",
				"-FocalPlaneXResolution", "-FocalPlaneYResolution", "-FocalPlaneResolutionUnit",
				"-DateTimeOriginal", "-CreateDate", "-ModifyDate",
				"-ISO", "-ExposureTime", "-FNumber",
				"-WhiteBalance",
				"-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
				"-GPSLatitudeRef", "-GPSLongitudeRef", "-GPSAltitudeRef",
				"-GPSDateStamp", "-GPSTimeStamp",
				str(enfused_path),
		], check=True)

		per_stack_xmp = enfused_path.parent / f"{enfused_path.name}.xmp"
		if not per_stack_xmp.exists():
				log(f"seeding {per_stack_xmp.name} from default_stack.xmp")
				subprocess.run(
						["cp", "--reflink=auto", str(DEFAULT_STACK_XMP), str(per_stack_xmp)],
						check=True,
				)

		log(f"darktable {per_stack_xmp.name} -> {fused_tiff.name}")
		subprocess.run([
				str(DARKTABLE_WRAPPER),
				str(enfused_path),
				str(per_stack_xmp),
				str(fused_tiff),
				"--core", "--conf", "plugins/imageio/format/tiff/bpp=16",
		], check=True)


def _fuse_one_group(group, tiff_dir, webp_dir, aligned_dir, enfused_dir):
		middle = group[len(group) // 2]
		stem = middle.stem
		fused_tiff = tiff_dir / f"{stem}_fused.tiff"
		fused_webp = webp_dir / f"{stem}_fused.webp"

		aligned = _align_stack(group, tiff_dir, aligned_dir, stem)
		if aligned is None:
				return
		enfused = _enfuse_stack(aligned, enfused_dir, stem)
		_darktable_finalize(enfused, fused_tiff, middle)

		if fused_webp.exists():
				return
		log(f"Converting {fused_tiff.name} -> WebP")
		subprocess.run(
				["cwebp", *CWEBP_ARGS, str(fused_tiff), "-o", str(fused_webp)],
				check=True,
		)
		# Same EXIF-copy pattern as the per-frame webps (exif_tags_from_cr2_to_webp.sh):
		# pull camera/GPS/etc. tags from the CR2 that represents this stack.
		subprocess.run([
				"exiftool", "-overwrite_original",
				"-TagsFromFile", str(middle),
				"-EXIF:all", "-GPS:all", "-XMP:all", "-IPTC:all",
				"-MakerNotes=", "-ThumbnailImage=", "-PreviewImage=",
				"-EXIF:PixelXDimension=", "-EXIF:PixelYDimension=",
				"-GPS:GPSDateStamp=",
				str(fused_webp),
		], check=True)
		# Orientation: copy from the middle frame's per-frame TIFF (not _fused).
		# align_image_stack only does sub-pixel jitter — not 90° rotations —
		# so the fused pixels share orientation with their per-frame source.
		# Reading from the per-frame TIFF picks up RT's =3 (or darktable's =1)
		# regardless of which raw processor produced it.
		middle_tiff = find_tiff(tiff_dir, middle.stem)
		subprocess.run([
				"exiftool", "-overwrite_original", "-n",
				"-TagsFromFile", str(middle_tiff),
				"-Orientation",
				str(fused_webp),
		], check=True)

def geotag(webp_dir, geotag_args):
		webp_files = sorted(webp_dir.glob("*.webp"))
		if not webp_files:
				log("No webp files to geotag")
				return
		geotag_project = SCRIPT_DIR / "../geotag"
		subprocess.run([
				"uv", "run",
				"--project", str(geotag_project),
				str(geotag_project / "geo_tag_photos.py"),
		] + geotag_args + [str(f) for f in webp_files], check=True)

if __name__ == "__main__":
		parser = argparse.ArgumentParser(
				description='CR2 raw photo processing pipeline.',
				formatter_class=argparse.RawDescriptionHelpFormatter,
				epilog=__doc__,
		)
		parser.add_argument('--correction', '-c', default=None,
												help='Time correction for geotagging (seconds or "auto", default: auto)')
		parser.add_argument('--csv-dir', default=None,
												help='Directory containing hillview CSV files (default: ~/GeoTrackingDumps)')
		args = parser.parse_args()

		geotag_args = []
		if args.correction is not None:
				geotag_args += ['--correction', args.correction]
		if args.csv_dir is not None:
				geotag_args += ['--csv-dir', args.csv_dir]

		tiff_dir = Path("tiff")
		webp_dir = Path("webp")
		aligned_dir = Path("aligned")
		enfused_dir = Path("enfused")
		setup_dirs()
		convert_all_cr2_to_tiff(tiff_dir)
		copy_cr2_tags_to_tiffs(tiff_dir)
		convert_all_tiff_to_webp(tiff_dir, webp_dir)
		copy_exif()
		fuse_brackets(tiff_dir, webp_dir, aligned_dir, enfused_dir)
		geotag(webp_dir, geotag_args)
