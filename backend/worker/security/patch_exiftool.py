"""Apply the narrow upstream fix for ExifTool CVE-2026-7580.

Source: exiftool/exiftool commit 5a8b6b6ead12b39e3f32f978a4efd0233facbb01,
lib/Image/ExifTool/GM.pm (13.54). Keep Debian's other code and packaging.
Fail the build if the expected code changes instead of guessing how to patch it.
"""
from pathlib import Path
import sys

OLD = '''            $units =~ tr/"\\\\//d; # (just to be safe, probably never happen)
            $$tagInfo{PrintConv} = $printConv{$units} || qq("\\$val $units");'''
NEW = r'''            $$tagInfo{PrintConv} = $printConv{$units} || qq("\$val \Q$units\E");'''


def patch(path):
    source = path.read_text()
    if source.count(NEW) == 1 and OLD not in source:
        return 'Upstream ExifTool GM escaping fix already present'
    if source.count(OLD) != 1 or NEW in source:
        raise RuntimeError('Unrecognized ExifTool GM.pm; review the upstream fix before building')
    path.write_text(source.replace(OLD, NEW))
    return 'Applied upstream ExifTool GM escaping fix (CVE-2026-7580)'


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/usr/share/perl5/Image/ExifTool/GM.pm')
    print(patch(path))
