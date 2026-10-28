#!/usr/bin/env python3
"""Compare the installed GM parser with the upstream conversion-escaping fix.

Only a temporary module copy is patched. The generated expression is inspected,
never evaluated. This does not demonstrate remote JPEG exploitability.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

source = Path('/usr/share/perl5/Image/ExifTool/GM.pm').read_text()
old = '''            $units =~ tr/"\\\\//d; # (just to be safe, probably never happen)
            $$tagInfo{PrintConv} = $printConv{$units} || qq("\\$val $units");'''
new = r'''            $$tagInfo{PrintConv} = $printConv{$units} || qq("\$val \Q$units\E");'''
already_fixed = source.count(new) == 1 and old not in source
assert already_fixed or source.count(old) == 1, 'Installed source differs; review the upstream patch again'
with tempfile.TemporaryDirectory() as work:
    root = Path(work)
    module = root / 'Image/ExifTool/GM.pm'
    module.parent.mkdir(parents=True)
    module.write_text(source.replace(old, new))
    results = {}
    for name, library in [('installed', '/review/probes'), ('upstream_fix', f'{root}:/review/probes')]:
        trace = root / (name + '.trace')
        env = {**os.environ, 'PERL5LIB': library, 'PERL5OPT': '-MHillviewTrace',
               'HILLVIEW_TRACE_FILE': str(trace)}
        result = subprocess.run(['perl', '/review/probes/exiftool_gm_control.pl'],
                                env=env, capture_output=True, text=True, check=True, timeout=10)
        assert 'GM_DICTIONARY' in trace.read_text()
        results[name] = result.stdout.strip()
    assert (r'unit\$marker' if already_fixed else 'unit$marker') in results['installed']
    assert r'unit\$marker' in results['upstream_fix']
    ordinary = {}
    for units in ('rpm', 'kph', 'widgets/s'):
        outputs = []
        for library in ('/review/probes', f'{root}:/review/probes'):
            env = {**os.environ, 'PERL5LIB': library, 'PERL5OPT': '-MHillviewTrace',
                   'HILLVIEW_TRACE_FILE': str(root / 'ordinary.trace')}
            output = subprocess.run(['perl', '/review/probes/exiftool_gm_control.pl', units],
                                    env=env, capture_output=True, text=True, check=True, timeout=10)
            formatted = [line for line in output.stdout.splitlines() if line.startswith('Formatted:')]
            assert len(formatted) == 1 and formatted[0] != 'Formatted: ', output.stdout
            outputs.append(formatted[0])
        assert outputs[0] == outputs[1], (units, outputs)
        ordinary[units] = outputs[0]
    results['ordinary_unit_compatibility'] = ordinary
    print(json.dumps(results, indent=2))
