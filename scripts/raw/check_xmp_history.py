#!/usr/bin/env python3
"""
Check (and optionally sync) darktable XMP history across a directory.

When stitching a panorama, every frame should have an identical darktable
history stack. Otherwise "applying the same style" produces visibly different
results per frame (different white balance, tone mapping, etc.).

Usage:
  check_xmp_history.py [directory] [--pattern GLOB] [--verbose]
  check_xmp_history.py [directory] --fix            # copy reference onto outliers
  check_xmp_history.py [directory] --fix --dry-run  # preview changes

Exits 0 if all XMPs share one history; 1 if there are mismatches.
"""

import argparse
import hashlib
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

HISTORY_RE = re.compile(r'<darktable:history>.*?</darktable:history>', re.S)
MASKS_RE = re.compile(r'<darktable:masks_history>.*?</darktable:masks_history>', re.S)
ENTRY_RE = re.compile(
    r'darktable:num="(\d+)"\s+'
    r'darktable:operation="([^"]+)"\s+'
    r'darktable:enabled="(\d+)"'
)
HISTORY_END_RE = re.compile(r'history_end="(\d+)"')

# Attributes on <rdf:Description> that together define the render pipeline.
# Keep the list tight — replacing unrelated attrs (timestamps, rating,
# DerivedFrom) would corrupt per-file metadata.
SYNCED_ATTRS = [
    "darktable:history_end",
    "darktable:history_current_hash",
    "darktable:iop_order_version",
    "darktable:iop_order_list",
    "darktable:xmp_version",
    "darktable:auto_presets_applied",
]


def parse_xmp(path: Path):
    data = path.read_text()
    m = HISTORY_RE.search(data)
    if not m:
        return None
    body = m.group(0)
    hist_hash = hashlib.md5(body.encode()).hexdigest()[:8]
    entries = [(int(n), op, en) for n, op, en in ENTRY_RE.findall(body)]
    end_m = HISTORY_END_RE.search(data)
    history_end = int(end_m.group(1)) if end_m else None
    return hist_hash, history_end, entries


def diff_entries(ref, other):
    ref_set = [(op, en) for _, op, en in ref]
    other_set = [(op, en) for _, op, en in other]
    missing = [x for x in ref_set if x not in other_set]
    extra = [x for x in other_set if x not in ref_set]
    return missing, extra


def sync_xmp(reference: Path, target: Path, dry_run: bool = False) -> bool:
    """Copy render-affecting pieces of `reference` onto `target`. Returns True
    on change, False if already identical. Writes a .bak before modifying."""
    ref_data = reference.read_text()
    tgt_data = target.read_text()

    # Replace the history and masks_history blocks.
    ref_hist = HISTORY_RE.search(ref_data)
    ref_masks = MASKS_RE.search(ref_data)
    if not ref_hist:
        raise RuntimeError(f"reference {reference} has no <darktable:history>")

    new_data = HISTORY_RE.sub(lambda _: ref_hist.group(0), tgt_data)
    if ref_masks:
        new_data = MASKS_RE.sub(lambda _: ref_masks.group(0), new_data)

    # Replace render-pipeline attributes on <rdf:Description>.
    for attr in SYNCED_ATTRS:
        m = re.search(rf'{re.escape(attr)}="([^"]*)"', ref_data)
        if not m:
            continue
        ref_val = m.group(1)
        pattern = rf'({re.escape(attr)}=")[^"]*(")'
        new_data, n = re.subn(pattern, rf'\g<1>{ref_val}\g<2>', new_data, count=1)
        if n == 0:
            # attribute missing from target — inject it before the closing `>`
            # of the opening <rdf:Description ...> tag
            new_data = re.sub(
                r'(<rdf:Description\b[^>]*?)(>)',
                rf'\1\n   {attr}="{ref_val}"\2',
                new_data, count=1,
            )

    if new_data == tgt_data:
        return False

    if dry_run:
        return True

    backup = target.with_suffix(target.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(target, backup)
    target.write_text(new_data)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Check darktable XMP history consistency across a directory.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('directory', nargs='?', default='.',
                        help='Directory to scan (default: current directory)')
    parser.add_argument('--pattern', default='*.xmp',
                        help='Glob pattern for sidecars (default: *.xmp)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show per-module diff for outliers')
    parser.add_argument('--fix', action='store_true',
                        help='Sync outlier XMPs to the largest group (writes .bak)')
    parser.add_argument('--dry-run', action='store_true',
                        help='With --fix, report what would change without writing')
    parser.add_argument('--reference', default=None,
                        help='With --fix, use this XMP as reference instead of '
                             'the largest group')
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    files = sorted(directory.glob(args.pattern))
    if not files:
        print(f"no files matching {args.pattern!r} in {directory}", file=sys.stderr)
        return 2

    groups = defaultdict(list)  # hist_hash -> [(path, history_end, entries)]
    for f in files:
        parsed = parse_xmp(f)
        if parsed is None:
            print(f"{f.name}  (no <darktable:history> block)")
            continue
        hist_hash, history_end, entries = parsed
        groups[hist_hash].append((f, history_end, entries))

    for f in files:
        parsed = parse_xmp(f)
        if parsed is None:
            continue
        hist_hash, history_end, _ = parsed
        print(f"{f.name}  hist={hist_hash}  history_end={history_end}")

    print()
    if len(groups) == 1:
        (hist_hash,) = groups.keys()
        print(f"OK: all {len(files)} files share history {hist_hash}")
        return 0

    # Pick the largest group as the reference
    ref_hash, ref_items = max(groups.items(), key=lambda kv: len(kv[1]))
    ref_entries = ref_items[0][2]
    print(f"MISMATCH: {len(groups)} distinct history stacks")
    for h, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        tag = " (reference)" if h == ref_hash else ""
        print(f"  hist={h}  count={len(items)}{tag}")
        for f, end, _ in items:
            print(f"    {f.name}  history_end={end}")

    if args.verbose:
        print()
        print(f"Module diff vs reference ({ref_hash}):")
        for h, items in groups.items():
            if h == ref_hash:
                continue
            _, _, entries = items[0]
            missing, extra = diff_entries(ref_entries, entries)
            print(f"  group {h}:")
            print(f"    missing vs reference: {missing or '(none)'}")
            print(f"    extra vs reference:   {extra or '(none)'}")

    if args.fix:
        if args.reference:
            reference = Path(args.reference)
            if not reference.is_file():
                print(f"error: reference not found: {reference}", file=sys.stderr)
                return 2
        else:
            reference = ref_items[0][0]
        print()
        print(f"{'Would sync' if args.dry_run else 'Syncing'} "
              f"outliers to reference: {reference.name}")
        changed = 0
        for h, items in groups.items():
            if h == ref_hash and not args.reference:
                continue
            for f, _, _ in items:
                if f == reference:
                    continue
                if sync_xmp(reference, f, dry_run=args.dry_run):
                    changed += 1
                    print(f"  {'[dry-run] ' if args.dry_run else ''}{f.name}")
        if args.dry_run:
            print(f"{changed} file(s) would be modified")
            return 1
        print(f"{changed} file(s) synced (originals backed up as .xmp.bak)")
        return 0 if changed else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
