#!/usr/bin/env python3
"""
List, disable, enable, or remove a named darktable module across every XMP
sidecar in a directory. Useful when darktable's GUI is confused about multiple
instances of the same module and you need a surgical edit.

Usage:
	xmp_module.py list      [dir] [--pattern GLOB] [--module NAME]
	xmp_module.py disable   [dir] [--pattern GLOB] --module NAME
	xmp_module.py enable    [dir] [--pattern GLOB] --module NAME
	xmp_module.py remove    [dir] [--pattern GLOB] --module NAME

Always writes a `.bak` alongside the first time a file is modified. Run
check_xmp_history.py afterward to verify all files still share one history.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# Match a single <rdf:li ... /> element from a darktable history stack.
LI_RE = re.compile(
		r'<rdf:li\b[^>]*?/>',
		re.S,
)

HISTORY_END_RE = re.compile(r'history_end="(\d+)"')


def li_operation(li: str) -> str | None:
		m = re.search(r'darktable:operation="([^"]+)"', li)
		return m.group(1) if m else None


def li_enabled(li: str) -> str | None:
		m = re.search(r'darktable:enabled="(\d+)"', li)
		return m.group(1) if m else None


def li_num(li: str) -> int | None:
		m = re.search(r'darktable:num="(\d+)"', li)
		return int(m.group(1)) if m else None


def li_multi_name(li: str) -> str:
		m = re.search(r'darktable:multi_name="([^"]*)"', li)
		return m.group(1) if m else ""


def set_enabled(li: str, value: str) -> str:
		return re.sub(r'(darktable:enabled=")[^"]*(")', rf'\g<1>{value}\g<2>', li, count=1)


def cmd_list(files, module: str | None):
		for f in files:
				data = f.read_text()
				hits = []
				for li in LI_RE.findall(data):
						op = li_operation(li)
						if op is None:
								continue
						if module and op != module:
								continue
						hits.append((li_num(li), op, li_enabled(li), li_multi_name(li)))
				if not hits:
						continue
				print(f"{f.name}:")
				for num, op, en, name in hits:
						tag = f" ({name})" if name else ""
						print(f"  [{num}] {op}  enabled={en}{tag}")
		return 0


def cmd_toggle(files, module: str, new_enabled: str):
		changed = 0
		for f in files:
				data = f.read_text()

				def transform(m):
						li = m.group(0)
						if li_operation(li) != module:
								return li
						if li_enabled(li) == new_enabled:
								return li
						return set_enabled(li, new_enabled)

				new_data = LI_RE.sub(transform, data)
				if new_data == data:
						continue
				backup = f.with_suffix(f.suffix + ".bak")
				if not backup.exists():
						shutil.copy2(f, backup)
				f.write_text(new_data)
				changed += 1
				print(f"  updated {f.name}")
		print(f"{changed} file(s) modified")
		return 0 if changed else 1


def cmd_remove(files, module: str):
		"""Remove all <rdf:li> entries for `module` and adjust history_end.

		Leaves num attributes on surviving entries untouched — darktable tolerates
		non-contiguous num values in practice; renumbering risks desyncing other
		references (masks, blend ops) that we don't parse here.
		"""
		changed = 0
		for f in files:
				data = f.read_text()
				removed = 0

				def transform(m):
						nonlocal removed
						li = m.group(0)
						if li_operation(li) == module:
								removed += 1
								return ""
						return li

				new_data = LI_RE.sub(transform, data)
				if removed == 0:
						continue

				# Decrement history_end by the number of removed entries so darktable
				# doesn't try to apply past the end of the stack.
				def fix_end(m):
						return f'history_end="{int(m.group(1)) - removed}"'

				new_data = HISTORY_END_RE.sub(fix_end, new_data, count=1)

				backup = f.with_suffix(f.suffix + ".bak")
				if not backup.exists():
						shutil.copy2(f, backup)
				f.write_text(new_data)
				changed += 1
				print(f"  {f.name}: removed {removed} entr{'y' if removed == 1 else 'ies'}")
		print(f"{changed} file(s) modified")
		return 0 if changed else 1


def main():
		parser = argparse.ArgumentParser(
				description="Edit a named module across darktable XMP sidecars.",
				formatter_class=argparse.RawDescriptionHelpFormatter,
				epilog=__doc__,
		)
		parser.add_argument("action", choices=["list", "enable", "disable", "remove"])
		parser.add_argument("directory", nargs="?", default=".")
		parser.add_argument("--pattern", default="*.xmp")
		parser.add_argument("--module", "-m", default=None,
												help="Module operation name (e.g. sigmoid, hazeremoval)")
		args = parser.parse_args()

		directory = Path(args.directory)
		if not directory.is_dir():
				print(f"error: not a directory: {directory}", file=sys.stderr)
				return 2
		files = sorted(directory.glob(args.pattern))
		if not files:
				print(f"no files matching {args.pattern!r} in {directory}", file=sys.stderr)
				return 2

		if args.action != "list" and not args.module:
				print("error: --module is required for enable/disable/remove", file=sys.stderr)
				return 2

		if args.action == "list":
				return cmd_list(files, args.module)
		if args.action == "enable":
				return cmd_toggle(files, args.module, "1")
		if args.action == "disable":
				return cmd_toggle(files, args.module, "0")
		if args.action == "remove":
				return cmd_remove(files, args.module)
		return 2


if __name__ == "__main__":
		sys.exit(main())
