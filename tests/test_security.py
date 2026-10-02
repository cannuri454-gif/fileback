"""Failure, filesystem boundary and persistence regression checks."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from fileback.store import Store


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.docs = self.base / 'docs'
        self.docs.mkdir()
        self.store = Store(self.base / 'vault')
        self.store.add_folder(self.docs)
        self.folder = self.store.folders()[0]['id']

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save(self, data=b'original', name='draft.txt'):
        (self.docs / name).write_bytes(data)
        self.store.scan()
        file = next(f for f in self.store.files() if f['path'] == name)
        return self.store.versions(file['id'])[0]['id']

    def test_alternate_stream_drive_and_escape_paths_rejected(self):
        for name in ('../secret', str(self.base / 'outside'), 'draft.txt:hidden', 'C:relative'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.capture(self.folder, name)

    def test_open_handle_outside_root_rejected_before_read(self):
        self.save()
        with patch('fileback.store.opened_path', return_value=self.base / 'private.txt'):
            with self.assertRaisesRegex(ValueError, 'outside'):
                self.store.read_source(self.folder, 'draft.txt', 1024)

    def test_text_comparison_cannot_read_vault(self):
        with self.assertRaises(ValueError):
            self.store.read_source(self.folder, '../vault/history.sqlite3', 1024)

    def test_sql_like_unicode_filename_roundtrip(self):
        name = "résumé'); DROP TABLE files;--.txt"
        version = self.save(b'\x00\xff\r\n', name)
        self.assertEqual(self.store.content(version), b'\x00\xff\r\n')
        self.assertEqual(len(self.store.files()), 1)

    def test_capture_failure_rolls_back_all_metadata(self):
        (self.docs / 'draft.txt').write_bytes(b'new')
        with patch.object(self.store, '_prune', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.capture(self.folder, 'draft.txt')
        self.assertEqual(self.store.stats()['versions'], 0)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM files').fetchone()[0], 0)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM blobs').fetchone()[0], 0)

    def test_evicted_current_content_can_be_saved_again(self):
        self.store.max_storage_bytes = 1
        (self.docs / 'draft.txt').write_bytes(b'unchanged')
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 0)
        self.store.max_storage_bytes = 1024
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 1)

    def test_concurrent_capture_does_not_duplicate_identical_versions(self):
        (self.docs / 'draft.txt').write_bytes(b'concurrent')
        failures = []
        def capture():
            try:
                self.store.capture(self.folder, 'draft.txt')
            except Exception as error:
                failures.append(error)
        workers = [threading.Thread(target=capture) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.store.stats()['versions'], 1)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_failed_recovery_removes_partial_copy(self):
        version = self.save()
        destination = self.base / 'recovered.txt'
        with patch('fileback.store.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store.restore_copy(version, destination)
        self.assertFalse(destination.exists())
        self.assertEqual((self.docs / 'draft.txt').read_bytes(), b'original')

    def test_modified_hash_and_truncated_stream_rejected(self):
        version = self.save()
        original = bytes(self.store.db.execute('SELECT data FROM blobs').fetchone()[0])
        for data in (original[:-1], b'', original + original):
            with self.subTest(data=data), self.store.db:
                self.store.db.execute('UPDATE blobs SET data=?', (data,))
            with self.assertRaises(ValueError):
                self.store.content(version)

    def test_abrupt_process_exit_rolls_back_uncommitted_transaction(self):
        self.save()
        code = "import sqlite3,sys,os; db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE'); db.execute('DELETE FROM versions'); os._exit(7)"
        child = subprocess.run([sys.executable, '-c', code, str(self.store.directory / 'history.sqlite3')], timeout=15)
        self.assertEqual(child.returncode, 7)
        self.assertEqual(self.store.stats()['versions'], 1)
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    @unittest.skipUnless(os.name == 'nt', 'Windows junction integration')
    def test_real_windows_junction_is_not_followed(self):
        target = self.base / 'private'
        target.mkdir()
        (target / 'secret.txt').write_text('not protected')
        junction = self.docs / 'linked'
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        command = f'New-Item -ItemType Junction -Path {quote(junction)} -Target {quote(target)} | Out-Null'
        # Literal-quoted, controlled temporary paths; no elevated access.
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertTrue(junction.is_junction())
        self.assertFalse(self.store.capture(self.folder, 'linked/secret.txt'))
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 0)
        # rmdir removes only the junction itself; the private target remains.
        junction.rmdir()
        self.assertEqual((target / 'secret.txt').read_text(), 'not protected')

    def test_many_files_and_retention_integrity(self):
        for index in range(250):
            (self.docs / f'{index:03d}.bin').write_bytes(bytes([index % 256]) * 1024)
        saved, errors = self.store.scan()
        self.assertEqual((saved, errors), (250, []))
        self.assertEqual(self.store.stats()['files'], 250)
        self.assertEqual(self.store.scan(), (0, []))
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
