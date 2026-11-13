"""Compile fixed helper source locally; never start LabVIEW or contact an executor."""
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parents[1]
for source in sorted((root / 'gui-tools').glob('*.aixml')):
    target = source.with_suffix('.vi')
    command = [sys.executable, str(root / 'scripts/compose_on_mac.py'), str(source), str(target), '--lv-version', '25']
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print('Helper compilation failed:', source.name, file=sys.stderr)
        print(result.stderr[-1500:], file=sys.stderr)
        raise SystemExit(result.returncode)
    print('Compiled locally:', target.name)
print('No LabVIEW application or remote connection was started.')
