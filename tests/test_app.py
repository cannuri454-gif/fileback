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
