import os
import unittest
from unittest.mock import patch
import settings
import dispatcher


class Settings(unittest.TestCase):
    def test_remote_disabled_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True), patch('dispatcher.ps') as remote:
            with self.assertRaises(RuntimeError):
                dispatcher.dispatch('offset_correction', {'RawCurrent': 1, 'Offset': 0})
            remote.assert_not_called()

    def test_host_must_not_be_an_ssh_option_or_shell_text(self):
        for host in ('-oProxyCommand=bad', 'host;bad', 'user@host', 'host\nother'):
            with patch.dict(os.environ, {'NI_AGENT_REMOTE_HOST': host}):
                with self.assertRaises(ValueError):
                    settings.remote_host()

    def test_windows_path_rejects_shell_metacharacters(self):
        for path in ("C:\\x';bad", r'C:\x\..\y', 'relative', 'C:\\x\nbad', 'C:\\x$bad'):
            with patch.dict(os.environ, {'NI_AGENT_WINDOWS_ROOT': path}):
                with self.assertRaises(ValueError):
                    settings.windows_root()

    def test_explicit_configuration(self):
        with patch.dict(os.environ, {'NI_AGENT_ENABLE_REMOTE': '1', 'NI_AGENT_REMOTE_HOST': 'labview-host',
                                    'NI_AGENT_WINDOWS_ROOT': r'C:\Local Agent'}):
            settings.require_remote()
            self.assertEqual(settings.windows_root(), r'C:\Local Agent')


if __name__ == '__main__':
    unittest.main()
