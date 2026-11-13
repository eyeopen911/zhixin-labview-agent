"""Scan publishable source without printing any matched credential value."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '__pycache__', 'tools', 'artifacts', 'designs', 'imports', 'interop', '.pytest_cache'}
BINARY = {'.vi', '.ctl', '.lvproj', '.lvlib', '.dll', '.exe', '.pfx', '.p12', '.pem', '.key', '.raw', '.zip', '.png', '.jpg'}
PATTERNS = [
    ('openai_key', re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}')),
    ('github_token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})')),
    ('slack_token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}')),
    ('aws_access_key', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('private_key', re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----')),
    ('credential_url', re.compile(r'https?://[^\s/"\'<>]+:[^\s/"\'<>]+@')),
    ('private_network_address', re.compile(r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b')),
    ('personal_home_path', re.compile(r'(?:/' + r'Users/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)')),
]
CREDENTIAL_ASSIGNMENT = re.compile(r'''(?im)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)\b\s*[:=]\s*['"]([^'"\r\n]{8,})['"]''')


def files(root):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True)
    if result.returncode == 0 and result.stdout:
        return [root / p.decode() for p in result.stdout.split(b'\0') if p]
    return [p for p in root.rglob('*') if p.is_file() and not any(k in SKIP for k in p.relative_to(root).parts)]


def scan(root):
    findings = []
    checked = []
    for path in files(root):
        rel = path.relative_to(root).as_posix()
        checked.append(rel)
        if path.suffix.lower() in BINARY or (path.name.startswith('.env') and path.name != '.env.example') or path.name in {'auth.json', 'hosts.yml'}:
            findings.append({'file': rel, 'line': 0, 'rule': 'excluded_file_type'})
            continue
        raw = path.read_bytes()
        if b'\x00' in raw:
            findings.append({'file': rel, 'line': 0, 'rule': 'binary_content'})
            continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            findings.append({'file': rel, 'line': 0, 'rule': 'non_utf8_file'})
            continue
        # Exact, deliberate rejection fixture; no general secret allowlist.
        if rel == 'tests_backend.py':
            text = text.replace('https://' + 'user:pass@example.com/v1', 'https://example.invalid/v1')
        for rule, pattern in PATTERNS:
            for match in pattern.finditer(text):
                findings.append({'file': rel, 'line': text.count('\n', 0, match.start()) + 1, 'rule': rule})
        if path.suffix == '.aixml':
            try:
                for item in ET.fromstring(text).iter():
                    label = re.sub(r'[^a-z]', '', item.get('_name', '').lower())
                    if item.tag in ('Control', 'Constant') and label in {'password', 'apikey', 'clientsecret', 'accesstoken', 'refreshtoken'} and item.get('value', ''):
                        findings.append({'file': rel, 'line': 0, 'rule': 'credential_xml_default'})
            except ET.ParseError:
                findings.append({'file': rel, 'line': 0, 'rule': 'invalid_xml'})
        for match in CREDENTIAL_ASSIGNMENT.finditer(text if path.suffix != '.aixml' else ''):
            if match.group(1) not in {'SECRET-EXAMPLE', '[REDACTED]', 'YOUR_MODEL_NAME'}:
                findings.append({'file': rel, 'line': text.count('\n', 0, match.start()) + 1, 'rule': 'credential_literal'})
    return {'ok': not findings, 'files_checked': len(checked), 'findings': findings,
            'scope': 'tracked files, or source-package files when no git index exists; matched values are never printed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = scan(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
