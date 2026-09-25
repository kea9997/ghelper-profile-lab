"""Release validation and transactional updater tests; no network or live app changes."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import updater


def release(tag='v0.4.1', content=b'MZtest executable'):
    return {
        'tag_name': tag, 'draft': False, 'prerelease': False, 'body': '변경 사항',
        'assets': [{
            'name': updater.ASSET_NAME, 'state': 'uploaded', 'size': len(content),
            'digest': 'sha256:' + hashlib.sha256(content).hexdigest(),
            'browser_download_url': (
                f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{updater.ASSET_NAME}'
            ),
        }],
    }


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_version_and_release_validation(self):
        info = updater.release_info(release())
        self.assertEqual(info['currentVersion'], updater.APP_VERSION)
        self.assertEqual(info['latestVersion'], '0.4.1')
        self.assertTrue(info['available'])
        self.assertFalse(updater.release_info(release('v0.4.0'))['available'])
        self.assertNotIn('downloadUrl', updater.public_info(info))
        for bad_tag in ('v0.4.1-beta', 'v0.4.1/evil', '0.4.1', 'v999999999999999999999.0.0'):
            with self.subTest(tag=bad_tag), self.assertRaises(ValueError):
                updater.release_info(release(bad_tag))

    def test_untrusted_release_metadata_cannot_choose_download_location(self):
        for field, value in [('digest', None), ('size', 200 * 1024 * 1024),
                             ('browser_download_url', 'https://other.example/download.exe'),
                             ('state', 'starter')]:
            with self.subTest(field=field):
                payload = release()
                payload['assets'][0][field] = value
                with self.assertRaises(ValueError):
                    updater.release_info(payload)

    def test_check_latest_and_verified_stage(self):
        content = b'MZtest executable'
        payload = json.dumps(release(content=content)).encode()
        info = updater.check_latest(lambda request, timeout: io.BytesIO(payload))
        staged = updater.download_verified(info, self.root, lambda request, timeout: io.BytesIO(content))
        self.assertEqual(staged.read_bytes(), content)
        self.assertEqual(staged.name, updater.ASSET_NAME)

    def test_corrupt_download_is_removed(self):
        info = updater.release_info(release())
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            updater.download_verified(info, self.root, lambda request, timeout: io.BytesIO(b'MZwrong executable'))
        self.assertEqual(list((self.root / 'updates').iterdir()), [])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows updater')
    def test_installer_stages_same_volume_and_starts_hidden_helper(self):
        executable = self.root / updater.ASSET_NAME
        executable.write_bytes(b'old executable')
        staged = self.root / 'staging' / updater.ASSET_NAME
        staged.parent.mkdir()
        staged.write_bytes(b'MZnew executable')
        launched = []
        def fake_popen(args, **kwargs):
            launched.append((args, kwargs))
        with patch.object(sys, 'frozen', True, create=True):
            updater.launch_installer(staged, self.root, executable=executable, popen=fake_popen)
        self.assertEqual(len(launched), 1)
        args, kwargs = launched[0]
        self.assertEqual(args[1:5], ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden'])
        self.assertTrue(kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW)
        script = base64.b64decode(args[-1]).decode('utf-16le')
        self.assertIn(str(executable), script)
        self.assertEqual(len(list(self.root.glob('.GHelperProfileLab-update-*.exe'))), 1)
        self.assertFalse(staged.exists())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows updater')
    def test_helper_restores_old_file_when_new_exe_cannot_launch(self):
        executable = self.root / updater.ASSET_NAME
        incoming = self.root / '.update.exe'
        status = self.root / 'status.txt'
        executable.write_bytes(b'old executable')
        incoming.write_bytes(b'not an executable')
        script = updater.updater_script(executable, incoming, status, 999999)
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand',
                        base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                       check=True, timeout=30, capture_output=True)
        self.assertEqual(executable.read_bytes(), b'old executable')
        self.assertEqual(status.read_text(), 'failed')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows updater')
    def test_helper_replaces_file_and_starts_verified_executable(self):
        executable = self.root / updater.ASSET_NAME
        incoming = self.root / '.update.exe'
        status = self.root / 'status.txt'
        executable.write_bytes(b'old executable')
        source = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/whoami.exe'
        incoming.write_bytes(source.read_bytes())
        script = updater.updater_script(executable, incoming, status, 999999)
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand',
                        base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                       check=True, timeout=30, capture_output=True)
        self.assertEqual(executable.read_bytes(), source.read_bytes())
        self.assertEqual(status.read_text(), 'updated')
        for _ in range(50):
            try:
                executable.unlink()
                break
            except PermissionError:
                time.sleep(.1)
        self.assertFalse(executable.exists(), 'helper-launched process did not release the test executable')


if __name__ == '__main__':
    unittest.main()
