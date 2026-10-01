import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fileback.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.folder = self.base / 'documents'
        self.folder.mkdir()
        self.store = Store(self.base / 'history')
        self.store.add_folder(self.folder)
        self.folder_id = self.store.folders()[0]['id']

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def write(self, text, name='essay.txt'):
        path = self.folder / name
        path.write_text(text, encoding='utf-8')
        self.store.scan()
        return path

    def test_capture_edit_and_restore_without_overwriting(self):
        path = self.write('First draft')
        self.write('Final draft')
        versions = self.store.versions(self.store.files()[0]['id'])
        self.assertEqual(len(versions), 2)
        recovered = self.base / 'recovered.txt'
        self.store.restore_copy(versions[-1]['id'], recovered)
        self.assertEqual(recovered.read_text(), 'First draft')
        self.assertEqual(path.read_text(), 'Final draft')
        with self.assertRaises(FileExistsError):
            self.store.restore_copy(versions[-1]['id'], path)
        self.assertEqual(path.read_text(), 'Final draft')

    def test_unchanged_files_do_not_add_versions(self):
        self.write('Same bytes')
        for _ in range(3):
            self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 1)

    def test_same_size_change_is_detected(self):
        path = self.write('aaaa')
        timestamp = path.stat().st_mtime_ns
        path.write_text('bbbb')
        os.utime(path, ns=(timestamp, timestamp))
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 2)

    def test_binary_and_empty_files(self):
        path = self.folder / 'binary.bin'
        path.write_bytes(b'\x00\xff\x11')
        self.write('', 'empty.txt')
        self.assertEqual(self.store.stats()['versions'], 2)
        contents = [self.store.content(self.store.versions(f['id'])[0]['id']) for f in self.store.files()]
        self.assertIn(b'', contents)
        self.assertIn(b'\x00\xff\x11', contents)

    def test_identical_content_is_stored_once(self):
        self.write('Identical', 'a.txt')
        self.write('Identical', 'b.txt')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM blobs').fetchone()[0], 1)
        self.assertEqual(self.store.stats()['versions'], 2)

    def test_deleted_file_stays_recoverable_and_recreation_is_saved(self):
        path = self.write('Keep me')
        path.unlink()
        self.store.scan()
        self.assertEqual(self.store.files()[0]['deleted'], 1)
        old = self.store.versions(self.store.files()[0]['id'])[0]
        self.assertEqual(self.store.content(old['id']), b'Keep me')
        self.write('Keep me')
        self.assertEqual(self.store.files()[0]['deleted'], 0)
        self.assertEqual(self.store.stats()['versions'], 2)

    def test_unavailable_folder_does_not_mark_files_deleted(self):
        self.write('Keep me')
        moved = self.base / 'moved'
        self.folder.rename(moved)
        _, errors = self.store.scan()
        self.assertTrue(errors)
        self.assertEqual(self.store.files()[0]['deleted'], 0)

    def test_incomplete_walk_does_not_mark_files_deleted(self):
        self.write('Keep me')
        def broken_walk(root, followlinks, onerror):
            onerror(PermissionError('Blocked'))
            return iter([])
        with patch('fileback.store.os.walk', broken_walk):
            _, errors = self.store.scan()
        self.assertTrue(errors)
        self.assertEqual(self.store.files()[0]['deleted'], 0)

    def test_pause_and_resume(self):
        self.write('Before')
        self.store.set_active(self.folder_id, False)
        self.write('After')
        self.assertEqual(self.store.stats()['versions'], 1)
        self.store.set_active(self.folder_id, True)
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 2)

    def test_version_retention_and_orphan_cleanup(self):
        self.store.versions_per_file = 2
        for text in ['one', 'two', 'three']:
            self.write(text)
        self.assertEqual(self.store.stats()['versions'], 2)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM blobs').fetchone()[0], 2)
        versions = self.store.versions(self.store.files()[0]['id'])
        self.assertEqual(self.store.content(versions[-1]['id']), b'two')

    def test_storage_budget_eviction(self):
        self.store.max_storage_bytes = 150
        for index in range(5):
            (self.folder / 'random.bin').write_bytes(os.urandom(100))
            self.store.scan()
        self.assertLessEqual(self.store.stats()['bytes'], 150)
        self.assertEqual(self.store.stats()['versions'], 1)

    def test_changed_during_read_is_not_committed(self):
        self.write('aaaa')
        real_open = Path.open
        class MutatingReader:
            def __enter__(inner):
                inner.stream = real_open(self.folder / 'essay.txt', 'rb')
                return inner
            def __exit__(inner, *args):
                inner.stream.close()
            def read(inner, n):
                data = inner.stream.read(n)
                with real_open(self.folder / 'essay.txt', 'w') as writer:
                    writer.write('longer changed text')
                return data
        with patch.object(Path, 'open', lambda *a, **k: MutatingReader()):
            self.assertFalse(self.store.capture(self.folder_id, 'essay.txt'))
        self.assertEqual(self.store.stats()['versions'], 1)

    def test_oversize_exclusions_and_storage_folder(self):
        self.store.max_file_bytes = 4
        self.write('too large')
        ignored = self.folder / 'node_modules'
        ignored.mkdir()
        (ignored / 'x').write_text('abc')
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 0)
        with self.assertRaises(ValueError):
            self.store.add_folder(self.store.directory)

    def test_path_escape_and_overlap_rejected(self):
        with self.assertRaises(ValueError):
            self.store.capture(self.folder_id, '../private.txt')
        sub = self.folder / 'nested'
        sub.mkdir()
        with self.assertRaises(ValueError):
            self.store.add_folder(sub)
        self.store.add_folder(self.folder)
        self.assertEqual(len(self.store.folders()), 1)

    def test_symlink_is_not_followed(self):
        target = self.base / 'private.txt'
        target.write_text('Private')
        link = self.folder / 'link.txt'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('Creating symlinks requires permission on this machine')
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 0)

    def test_corruption_stops_recovery(self):
        self.write('Original')
        version = self.store.versions(self.store.files()[0]['id'])[0]
        import zlib
        with self.store.db:
            self.store.db.execute('UPDATE blobs SET data=?', (zlib.compress(b'Tampered'),))
        with self.assertRaises(ValueError):
            self.store.restore_copy(version['id'], self.base / 'restore.txt')
        self.assertFalse((self.base / 'restore.txt').exists())

    def test_restart_preserves_history(self):
        self.write('Persistent')
        self.store.close()
        self.store = Store(self.base / 'history')
        self.store.scan()
        self.assertEqual(self.store.stats()['versions'], 1)
        version = self.store.versions(self.store.files()[0]['id'])[0]
        self.assertEqual(self.store.content(version['id']), b'Persistent')

    def test_modified_compressed_data_cannot_expand_past_declared_size(self):
        import zlib
        self.write('small')
        version = self.store.versions(self.store.files()[0]['id'])[0]
        for compressed in [zlib.compress(b'x' * 1024**2), b'not a zlib stream', zlib.compress(b'small') + b'extra']:
            with self.store.db:
                self.store.db.execute('UPDATE blobs SET data=?', (compressed,))
            with self.assertRaises(ValueError):
                self.store.content(version['id'])

    def test_invalid_saved_size_stops_recovery(self):
        self.write('small')
        version = self.store.versions(self.store.files()[0]['id'])[0]
        with self.store.db:
            self.store.db.execute('UPDATE blobs SET size=?', (self.store.max_file_bytes + 1,))
        with self.assertRaises(ValueError):
            self.store.content(version['id'])

    def test_link_guard_without_admin_permissions(self):
        self.write('small')
        with patch.object(Path, 'is_symlink', return_value=True):
            self.assertFalse(self.store.capture(self.folder_id, 'essay.txt'))


if __name__ == '__main__':
    unittest.main()
