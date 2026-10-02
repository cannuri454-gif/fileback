"""Desktop smoke tests: real Tk widgets and the actual worker thread."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from fileback.app import App
from fileback.store import Store


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.docs = self.base/'docs'
        self.docs.mkdir()
        self.source = self.docs/'draft.txt'
        self.source.write_text('Earlier draft\n')
        self.store = Store(self.base/'history')
        self.store.add_folder(self.docs)
        self.store.scan()
        self.source.write_text('Later draft\n')
        self.store.scan()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, self.store, interval=0.1)
        self.root.withdraw()

    def tearDown(self):
        self.app.close()
        deadline = time.monotonic()+5
        while not self.app.closed and time.monotonic()<deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(self.app.closed, 'Desktop worker did not shut down cleanly')
        self.temp.cleanup()

    def select_oldest(self):
        file = self.app.files_tree.get_children()[0]
        self.app.files_tree.selection_set(file)
        self.app.select_file()
        version = self.app.version_tree.get_children()[-1]
        self.app.version_tree.selection_set(version)
        self.app.preview()

    def test_preview_and_diff(self):
        self.select_oldest()
        self.assertIn('Earlier draft', self.app.preview_text.get('1.0', 'end'))
        self.app.diff_mode.set(True)
        self.app.preview()
        text = self.app.preview_text.get('1.0', 'end')
        self.assertIn('-Earlier draft', text)
        self.assertIn('+Later draft', text)

    def test_restore_from_interface(self):
        self.select_oldest()
        target = self.base/'recovered.txt'
        with patch('fileback.app.filedialog.asksaveasfilename', return_value=str(target)), patch('fileback.app.messagebox.showinfo'):
            self.app.restore()
        self.assertEqual(target.read_text(), 'Earlier draft\n')
        self.assertEqual(self.source.read_text(), 'Later draft\n')

    def test_pause_controls_and_search(self):
        self.app.toggle_pause()
        self.assertTrue(self.app.paused.is_set())
        self.app.toggle_pause()
        self.assertFalse(self.app.paused.is_set())
        self.app.folder_list.selection_set(0)
        self.app.toggle_folder()
        self.assertFalse(self.store.folders()[0]['active'])
        self.app.toggle_folder()
        self.assertTrue(self.store.folders()[0]['active'])
        self.app.search.set('not here')
        self.assertEqual(len(self.app.files_tree.get_children()), 0)
        self.app.search.set('draft')
        self.assertEqual(len(self.app.files_tree.get_children()), 1)

    def test_worker_detects_a_real_edit(self):
        self.source.write_text('Detected by background worker\n')
        self.app.wake.set()
        deadline = time.monotonic()+3
        while self.store.stats()['versions'] < 3 and time.monotonic()<deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertEqual(self.store.stats()['versions'], 3)

    def test_existing_destination_refused_in_interface(self):
        self.select_oldest()
        with patch('fileback.app.filedialog.asksaveasfilename', return_value=str(self.source)), patch('fileback.app.messagebox.showerror') as error:
            self.app.restore()
        error.assert_called_once()
        self.assertEqual(self.source.read_text(), 'Later draft\n')

    def test_binary_preview_and_missing_current_file(self):
        self.select_oldest()
        self.source.unlink()
        self.app.diff_mode.set(True)
        self.app.preview()
        self.assertIn('current file is missing', self.app.preview_text.get('1.0', 'end'))
        self.source.write_bytes(b'\x00\xff')
        self.store.scan()
        self.app.diff_mode.set(False)
        self.app.refresh_versions()
        self.app.version_tree.selection_set(self.app.version_tree.get_children()[0])
        self.app.preview()
        self.assertIn('not a UTF-8 text file', self.app.preview_text.get('1.0', 'end'))

    def test_comparison_rejects_changed_file_boundary(self):
        self.select_oldest()
        self.app.diff_mode.set(True)
        with patch.object(self.store, 'read_source', side_effect=ValueError('File is outside the protected folder or uses a link.')):
            self.app.preview()
        self.assertIn('outside the protected folder', self.app.preview_text.get('1.0', 'end'))

    def test_damaged_history_recovery_shows_error(self):
        self.select_oldest()
        with self.store.db:
            self.store.db.execute('UPDATE blobs SET data=?', (b'corrupt',))
        target = self.base / 'copy.txt'
        with patch('fileback.app.filedialog.asksaveasfilename', return_value=str(target)), patch('fileback.app.messagebox.showerror') as error:
            self.app.restore()
        error.assert_called_once()
        self.assertFalse(target.exists())

    def test_invalid_folder_and_cancelled_folder_dialog(self):
        with patch('fileback.app.filedialog.askdirectory', return_value=str(self.base / 'missing')), patch('fileback.app.messagebox.showerror') as error:
            self.app.add_folder()
            error.assert_called_once()
        with patch('fileback.app.filedialog.askdirectory', return_value=''):
            self.app.add_folder()
        self.assertEqual(len(self.store.folders()), 1)

    def test_background_error_is_visible_and_check_when_paused(self):
        self.app.messages.put(('error', 'history unavailable'))
        self.root.after_cancel(self.app.pump_timer)
        self.app.pump()
        self.assertIn('history unavailable', self.app.status.cget('text'))
        self.app.toggle_pause()
        self.app.check_now()
        self.assertIn('Watching is paused', self.app.status.cget('text'))
