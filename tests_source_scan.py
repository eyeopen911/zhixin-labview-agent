import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

module_path = Path(__file__).parent / 'scripts' / 'scan_source.py'
spec = importlib.util.spec_from_file_location('source_scan', module_path)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class SourceScan(unittest.TestCase):
    def test_token_is_blocked_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            value = 'sk-' + 'A' * 32
            (root / 'settings.py').write_text('value = ' + repr(value))
            report = scanner.scan(root)
            self.assertFalse(report['ok'])
            self.assertNotIn(value, json.dumps(report))
            self.assertEqual(report['findings'][0]['rule'], 'openai_key')

    def test_xml_unwired_password_port_is_not_a_credential(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'helper.aixml').write_text('<VI><Node inputs="' + 'password:' + '" outputs="value:" /></VI>')
            self.assertTrue(scanner.scan(root)['ok'])
            (root / 'helper.aixml').write_text('<VI><Constant _name="password" type="string" value="a-long-secret" /></VI>')
            self.assertFalse(scanner.scan(root)['ok'])

    def test_tracked_scope_does_not_publish_untracked_local_env(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'README.md').write_text('Source only')
            (root / '.env').write_text('API_KEY=' + 'sk-' + 'B' * 32)
            subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
            report = scanner.scan(root)
            self.assertTrue(report['ok'])
            self.assertEqual(report['files_checked'], 1)


if __name__ == '__main__':
    unittest.main()
