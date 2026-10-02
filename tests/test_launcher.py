"""A failed packaged check must report an error instead of opening a dialog."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run


class LauncherTests(unittest.TestCase):
    def test_failed_self_test_records_error_and_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'check.log'
            with patch.dict(os.environ, {'FILEBACK_SELF_TEST_LOG': str(log)}), \
                    patch('sys.argv', ['Fileback.exe', '--self-test']), \
                    patch('fileback.app.main', side_effect=RuntimeError('fictional failure')):
                with self.assertRaises(SystemExit) as raised:
                    run.launch()
            self.assertEqual(raised.exception.code, 1)
            self.assertIn('RuntimeError: fictional failure', log.read_text())
            self.assertNotIn('Passed', log.read_text())

    def test_successful_self_test_records_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'check.log'
            with patch.dict(os.environ, {'FILEBACK_SELF_TEST_LOG': str(log)}), \
                    patch('sys.argv', ['Fileback.exe', '--self-test']), \
                    patch('fileback.app.main') as main:
                run.launch()
            main.assert_called_once_with()
            self.assertTrue(log.read_text().endswith('Passed\n'))
