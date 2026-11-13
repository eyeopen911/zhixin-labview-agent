"""Report dependency readiness without reading credentials or contacting Windows."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
root = Path(__file__).resolve().parents[1]
bundle = Path(os.environ.get('NI_AGENT_LABVIEW_MCP_BIN') or root / 'tools/labview-mcp-release/package/bin')
report = {
    'python': sys.version.split()[0],
    'codex_cli_found': shutil.which('codex') is not None,
    'ssh_found': shutil.which('ssh') is not None,
    'scp_found': shutil.which('scp') is not None,
    'pillow_installed': importlib.util.find_spec('PIL') is not None,
    'lxml_installed': importlib.util.find_spec('lxml') is not None,
    'upstream_composer_found': (bundle / 'scripts/aixml-pylabview/aixml2vi.py').is_file(),
    'upstream_reader_found': (bundle / 'pylabview/app/pylabview/readRSRC.py').is_file(),
    'remote_execution_enabled': os.environ.get('NI_AGENT_ENABLE_REMOTE', '').lower() in ('1', 'true'),
    'model_key_configured': bool(os.environ.get('NI_AGENT_API_KEY')),
    'remote_contacted': False,
}
print(json.dumps(report, indent=2))
