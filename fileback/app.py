"""Windows-first desktop interface, using only Python's standard library."""
from __future__ import annotations
import argparse
import difflib
import os
from pathlib import Path
import queue
import threading
import time
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .store import Store

BG = '#f3f4ee'
INK = '#25322d'
GREEN = '#37624c'


def size_label(n):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}'
        n /= 1024


class App:
    def __init__(self, root, store, interval=5):
        self.root, self.store, self.interval = root, store, interval
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.paused = threading.Event()
        self.closed = False
        self.file_rows = {}
        self.version_rows = {}
        self.current_file = None
        self.last_scan = 'Waiting for first check'
        root.title('Fileback')
        root.geometry('1180x780')
        root.minsize(940, 660)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=INK)
        style.configure('TButton', padding=(13, 9), borderwidth=0)
        style.configure('Accent.TButton', background=GREEN, foreground='white')
        style.map('Accent.TButton', background=[('active', '#294e3b')])
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=28, borderwidth=0)
        style.configure('Treeview.Heading', background='#e7ebe3', font=('Segoe UI', 9, 'bold'), padding=8)
        style.map('Treeview', background=[('selected', '#dbe9dc')], foreground=[('selected', INK)])
        self.build()
        self.refresh()
        self.worker = threading.Thread(target=self.watch, daemon=True)
        self.worker.start()
        self.pump_timer = self.root.after(250, self.pump)

    def label(self, parent, text, font=('Segoe UI', 10), **kwargs):
        return tk.Label(parent, text=text, font=font, bg=kwargs.pop('bg', BG), fg=kwargs.pop('fg', INK), **kwargs)

    def build(self):
        sidebar = tk.Frame(self.root, bg='#23382f', width=235)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        self.label(sidebar, 'Fileback', ('Segoe UI', 25, 'bold'), bg='#23382f', fg='#def0d1').pack(anchor='w', padx=24, pady=(28, 8))
        self.label(sidebar, 'Local file history', bg='#23382f', fg='#becdc1').pack(anchor='w', padx=24)
        self.label(sidebar, 'PROTECTED FOLDERS', ('Segoe UI', 9, 'bold'), bg='#23382f', fg='#becdc1').pack(anchor='w', padx=24, pady=(36, 12))
        self.folder_list = tk.Listbox(sidebar, bg='#2d4439', fg='white', selectbackground='#4d7259', bd=0, highlightthickness=0, font=('Segoe UI', 10), height=9, exportselection=False)
        self.folder_list.pack(fill='x', padx=18)
        self.folder_list.bind('<<ListboxSelect>>', self.folder_selected)
        self.folder_info = self.label(sidebar, 'Choose a folder to start.', bg='#23382f', fg='#becdc1', wraplength=194, justify='left')
        self.folder_info.pack(fill='x', padx=20, pady=12)
        ttk.Button(sidebar, text='+ Protect a folder', style='Accent.TButton', command=self.add_folder).pack(fill='x', padx=18, pady=(5, 8))
        self.folder_toggle = ttk.Button(sidebar, text='Pause selected folder', command=self.toggle_folder, state='disabled')
        self.folder_toggle.pack(fill='x', padx=18)
        self.label(sidebar, 'STAYS ON THIS COMPUTER\nNo account. No cloud upload.', bg='#23382f', fg='#becdc1', justify='left', font=('Segoe UI', 9)).pack(side='bottom', anchor='w', padx=24, pady=28)

        main = tk.Frame(self.root, bg=BG)
        main.pack(side='left', fill='both', expand=True, padx=26, pady=25)
        header = tk.Frame(main, bg=BG)
        header.pack(fill='x')
        self.label(header, 'Your file history', ('Segoe UI', 25, 'bold')).pack(side='left')
        self.pause_button = ttk.Button(header, text='Pause watching', command=self.toggle_pause)
        self.pause_button.pack(side='right', padx=(8, 0))
        ttk.Button(header, text='Check now', command=self.check_now).pack(side='right')
        self.label(main, 'Browse earlier versions and recover a copy.', fg='#6c786d').pack(anchor='w', pady=(6, 17))
        self.stats_label = self.label(main, '', font=('Segoe UI', 10, 'bold'))
        self.stats_label.pack(anchor='w', pady=(0, 15))
        searchbar = tk.Frame(main, bg=BG)
        searchbar.pack(fill='x', pady=(0, 10))
        self.label(searchbar, 'FILE HISTORY', ('Segoe UI', 9, 'bold')).pack(side='left')
        self.search = tk.StringVar()
        self.search.trace_add('write', lambda *_: self.refresh_files())
        ttk.Entry(searchbar, textvariable=self.search, width=30).pack(side='right')
        self.label(searchbar, 'Find a file  ', fg='#6c786d').pack(side='right')
        self.files_tree = self.tree(main, ['name', 'status', 'versions', 'latest'], ['File / folder', 'Status', 'Versions', 'Last saved'], [365, 90, 70, 150], height=4)
        self.files_tree.bind('<<TreeviewSelect>>', self.select_file)
        details = tk.Frame(main, bg=BG)
        details.pack(fill='x', pady=(17, 10))
        self.detail_title = self.label(details, 'Pick a file to see its history', ('Segoe UI', 12, 'bold'))
        self.detail_title.pack(side='left')
        self.restore_button = ttk.Button(details, text='Recover a copy…', style='Accent.TButton', command=self.restore, state='disabled')
        self.restore_button.pack(side='right')
        self.version_tree = self.tree(main, ['when', 'size'], ['Saved version', 'File size'], [580, 120], height=2)
        self.version_tree.bind('<<TreeviewSelect>>', self.preview)
        previewbar = tk.Frame(main, bg=BG)
        previewbar.pack(fill='x', pady=(12, 6))
        self.label(previewbar, 'PREVIEW', ('Segoe UI', 9, 'bold')).pack(side='left')
        self.diff_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(previewbar, text='Compare with current file', variable=self.diff_mode, command=self.preview).pack(side='right')
        preview_frame = tk.Frame(main, bg='white')
        preview_frame.pack(fill='both', expand=True)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.preview_text = tk.Text(preview_frame, height=7, width=1, bg='white', fg=INK, font=('Consolas', 10), bd=0, padx=12, pady=10, wrap='none', state='disabled')
        self.preview_text.grid(row=0, column=0, sticky='nsew')
        preview_y = ttk.Scrollbar(preview_frame, orient='vertical', command=self.preview_text.yview)
        preview_y.grid(row=0, column=1, sticky='ns')
        preview_x = ttk.Scrollbar(preview_frame, orient='horizontal', command=self.preview_text.xview)
        preview_x.grid(row=1, column=0, sticky='ew')
        self.preview_text.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)
        self.preview_text.tag_configure('add', foreground='#267142')
        self.preview_text.tag_configure('remove', foreground='#a14039')
        self.write_preview('Your saved versions will appear here. Protect a folder to begin.')
        self.status = self.label(main, '', fg='#6c786d', anchor='w', wraplength=800, justify='left', font=('Segoe UI', 9))
        self.status.pack(fill='x', pady=(12, 4))
        footer = self.label(main, f'Checks every {self.interval} seconds · Files up to 50 MB · 50 versions per file · 1 GB of saved content', fg='#6c786d', font=('Segoe UI', 8))
        footer.pack(side='bottom', anchor='w', before=header)
        self.status.pack_forget()
        self.status.pack(side='bottom', fill='x', pady=(12, 4), before=header)

    def tree(self, parent, columns, headings, widths, height):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill='x')
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=height, selectmode='browse')
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=50, stretch=col == columns[0])
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(side='left', fill='x', expand=True)
        return tree

    def watch(self):
        while not self.stop.is_set():
            if not self.paused.is_set():
                try:
                    saved, errors = self.store.scan()
                    self.messages.put(('scan', saved, errors))
                except Exception as error:
                    self.messages.put(('error', str(error)))
            self.wake.wait(self.interval)
            self.wake.clear()

    def pump(self):
        if self.stop.is_set():
            return
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            if message[0] == 'scan':
                self.last_scan = f'Last checked {time.strftime("%H:%M:%S")}'
                self.status.configure(text=message[2][0] if message[2] else f'{self.last_scan} · {message[1]} new versions saved')
                self.refresh_files()
                self.update_stats()
                self.refresh_versions()
            else:
                self.status.configure(text=f'Could not save history: {message[1]}')
        self.pump_timer = self.root.after(250, self.pump)

    def refresh(self):
        selected = self.folder_list.curselection()
        self.folder_rows = self.store.folders()
        self.folder_list.delete(0, 'end')
        for folder in self.folder_rows:
            self.folder_list.insert('end', ('● ' if folder['active'] else 'Ⅱ ') + Path(folder['path']).name)
        if selected and selected[0] < len(self.folder_rows):
            self.folder_list.selection_set(selected[0])
        self.folder_selected()
        self.refresh_files()
        self.update_stats()

    def folder_selected(self, _=None):
        selected = self.folder_list.curselection()
        if not selected:
            self.folder_toggle.configure(state='disabled')
            self.folder_info.configure(text='Select a folder to view its details.' if self.folder_rows else 'Choose a folder to start.')
            return
        folder = self.folder_rows[selected[0]]
        self.folder_info.configure(text=folder['path'])
        self.folder_toggle.configure(state='normal', text='Pause selected folder' if folder['active'] else 'Resume selected folder')

    def add_folder(self):
        path = filedialog.askdirectory(title='Choose a folder to protect', parent=self.root)
        if path:
            try:
                self.store.add_folder(path)
                self.refresh()
                self.wake.set()
            except (ValueError, OSError) as error:
                messagebox.showerror('Could not protect this folder', str(error), parent=self.root)

    def toggle_folder(self):
        selected = self.folder_list.curselection()
        if selected:
            folder = self.folder_rows[selected[0]]
            self.store.set_active(folder['id'], not folder['active'])
            self.refresh()
            self.wake.set()

    def toggle_pause(self):
        if self.paused.is_set():
            self.paused.clear()
            self.pause_button.configure(text='Pause watching')
            self.status.configure(text='Watching resumed. Checking your folders…')
            self.wake.set()
        else:
            self.paused.set()
            self.pause_button.configure(text='Resume watching')
            self.status.configure(text='Watching paused. A check already in progress may finish.')

    def check_now(self):
        if self.paused.is_set():
            self.status.configure(text='Watching is paused. Resume watching to check your folders.')
        else:
            self.status.configure(text='Checking your folders…')
            self.wake.set()

    def update_stats(self):
        stats = self.store.stats()
        self.stats_label.configure(text=f'{stats["files"]} files protected     /     {stats["versions"]} saved versions     /     {size_label(stats["bytes"])} stored')

    def refresh_files(self):
        selected = self.files_tree.selection()
        rows = self.store.files(self.search.get())
        self.file_rows = {str(r['id']): r for r in rows}
        self.files_tree.delete(*self.files_tree.get_children())
        for row in rows:
            self.files_tree.insert('', 'end', iid=str(row['id']), values=(row['path'] + '  ·  ' + Path(row['folder_path']).name, 'Deleted' if row['deleted'] else 'Saved', row['versions'], time.strftime('%d %b %H:%M:%S', time.localtime(row['latest']))))
        if selected and selected[0] in self.file_rows:
            self.files_tree.selection_set(selected[0])
        elif self.current_file and str(self.current_file['id']) not in self.file_rows:
            self.current_file = None
            self.refresh_versions()

    def select_file(self, _=None):
        selected = self.files_tree.selection()
        if selected:
            self.current_file = self.file_rows[selected[0]]
            self.refresh_versions()

    def refresh_versions(self):
        selected = self.version_tree.selection()
        rows = self.store.versions(self.current_file['id']) if self.current_file else []
        self.version_rows = {str(r['id']): r for r in rows}
        self.version_tree.delete(*self.version_tree.get_children())
        for row in rows:
            self.version_tree.insert('', 'end', iid=str(row['id']), values=(time.strftime('%d %b %Y · %H:%M:%S', time.localtime(row['created'])), size_label(row['size'])))
        self.detail_title.configure(text=Path(self.current_file['path']).name if self.current_file else 'Pick a file to see its history')
        if rows:
            self.version_tree.selection_set(selected[0] if selected and selected[0] in self.version_rows else str(rows[0]['id']))
            self.preview()
        else:
            self.restore_button.configure(state='disabled')
            self.write_preview('Pick a file to see saved versions.')

    def write_preview(self, text):
        self.preview_text.configure(state='normal')
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', text)
        if self.diff_mode.get():
            for number, line in enumerate(text.splitlines(), 1):
                if line.startswith('+'):
                    self.preview_text.tag_add('add', f'{number}.0', f'{number}.end')
                elif line.startswith('-'):
                    self.preview_text.tag_add('remove', f'{number}.0', f'{number}.end')
        self.preview_text.configure(state='disabled')

    def preview(self, _=None):
        selected = self.version_tree.selection()
        if not selected or not self.current_file:
            return
        self.restore_button.configure(state='normal')
        version = self.version_rows.get(selected[0])
        if not version:
            return
        if version['size'] > 1024**2:
            self.write_preview('Preview is limited to text files under 1 MB. You can still recover this file.')
            return
        try:
            data = self.store.content(version['id'])
            if b'\x00' in data:
                raise UnicodeError()
            text = data.decode('utf-8-sig')
            if self.diff_mode.get():
                path = Path(self.current_file['folder_path']) / self.current_file['path']
                if not path.is_file():
                    self.write_preview('The current file is missing. Switch off comparison to view the saved version.')
                    return
                current = self.store.read_source(self.current_file['folder_id'], self.current_file['path'], 1024**2)
                text = '\n'.join(difflib.unified_diff(text.splitlines(), current.decode('utf-8-sig').splitlines(), fromfile='Saved version', tofile='Current file', lineterm='')) or 'No text changes between this version and the current file.'
            self.write_preview(text or '(Empty file)')
        except UnicodeError:
            self.write_preview('This is not a UTF-8 text file. Recover a copy to open it in its usual app.')
        except (OSError, ValueError) as error:
            self.write_preview(str(error))

    def restore(self):
        selected = self.version_tree.selection()
        if not selected or not self.current_file:
            return
        original = Path(self.current_file['path'])
        suggested = f'{original.stem}.recovered-{time.strftime("%Y%m%d-%H%M%S")}{original.suffix}'
        destination = filedialog.asksaveasfilename(parent=self.root, title='Recover as a new copy', initialfile=suggested, initialdir=self.current_file['folder_path'])
        if not destination:
            return
        try:
            self.store.restore_copy(int(selected[0]), destination)
            self.status.configure(text=f'Recovered a copy: {destination}')
            messagebox.showinfo('Your copy is ready', f'Saved to:\n{destination}\n\nYour current file was not changed.', parent=self.root)
        except FileExistsError:
            messagebox.showerror('Choose a new filename', 'That file already exists. Fileback never overwrites files during recovery.', parent=self.root)
        except (OSError, ValueError) as error:
            messagebox.showerror('Could not recover', str(error), parent=self.root)

    def close(self):
        if self.stop.is_set():
            return
        self.stop.set()
        self.wake.set()
        self.root.after_cancel(self.pump_timer)
        self.root.withdraw()
        self.finish_close()

    def finish_close(self):
        if self.worker.is_alive():
            self.root.after(100, self.finish_close)
        else:
            self.store.close()
            self.closed = True
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description='Fileback — local file history')
    parser.add_argument('--data-dir', type=Path, help='Use a separate history folder (useful for testing)')
    parser.add_argument('--self-test', action='store_true', help='Exercise the packaged app with temporary fictional files')
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            docs = base / 'documents'
            docs.mkdir()
            source = docs / 'draft.txt'
            source.write_text('Earlier draft\n', encoding='utf-8')
            store = Store(base / 'history')
            store.add_folder(docs)
            store.scan()
            source.write_text('Current draft\n', encoding='utf-8')
            store.scan()
            root = tk.Tk()
            root.withdraw()
            app = App(root, store)
            root.withdraw()
            versions = store.versions(store.files()[0]['id'])
            store.restore_copy(versions[-1]['id'], base / 'recovered.txt')
            if (base / 'recovered.txt').read_text() != 'Earlier draft\n' or source.read_text() != 'Current draft\n':
                raise RuntimeError('Packaged recovery self-test failed.')
            app.close()
            deadline = time.monotonic() + 10
            while not app.closed and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            if not app.closed:
                raise RuntimeError('Packaged worker did not stop.')
        return
    directory = args.data_dir or Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'Fileback'
    root = tk.Tk()
    try:
        store = Store(directory)
    except Exception as error:
        root.withdraw()
        messagebox.showerror('Fileback could not start', f'Could not open the history folder:\n{error}', parent=root)
        root.destroy()
        return
    App(root, store)
    root.mainloop()


if __name__ == '__main__':
    main()
