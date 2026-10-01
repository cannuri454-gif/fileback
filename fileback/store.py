"""Snapshot storage. No network calls; source files are never modified."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import time
import zlib

EXCLUDED = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '$RECYCLE.BIN', 'System Volume Information'}


class Store:
    def __init__(self, directory, *, max_file_bytes=50 * 1024**2, max_storage_bytes=1024**3, versions_per_file=50):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_bytes
        self.max_storage_bytes = max_storage_bytes
        self.versions_per_file = versions_per_file
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / 'history.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS folders(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS blobs(hash TEXT PRIMARY KEY, data BLOB NOT NULL, size INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, folder_id INTEGER NOT NULL REFERENCES folders(id), path TEXT NOT NULL, current_hash TEXT, deleted INTEGER NOT NULL DEFAULT 0, UNIQUE(folder_id,path));
            CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), hash TEXT NOT NULL REFERENCES blobs(hash), created REAL NOT NULL, size INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS version_file ON versions(file_id,created);
        ''')
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    def add_folder(self, path):
        path = Path(path).resolve()
        if not path.is_dir():
            raise ValueError('Choose an existing folder.')
        if path == self.directory or path.is_relative_to(self.directory):
            raise ValueError('The history storage folder cannot watch itself.')
        with self.lock, self.db:
            for row in self.db.execute('SELECT path FROM folders WHERE active=1'):
                existing = Path(row['path'])
                if path != existing and (path.is_relative_to(existing) or existing.is_relative_to(path)):
                    raise ValueError('This overlaps a watched folder. Choose one folder to cover both.')
            self.db.execute('INSERT INTO folders(path) VALUES(?) ON CONFLICT(path) DO UPDATE SET active=1', (str(path),))

    def folders(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM folders ORDER BY path')]

    def set_active(self, folder_id, active):
        with self.lock, self.db:
            self.db.execute('UPDATE folders SET active=? WHERE id=?', (int(active), folder_id))

    def capture(self, folder_id, relative):
        """Read one stable version, then atomically commit bytes and metadata."""
        with self.lock:
            folder = self.db.execute('SELECT path FROM folders WHERE id=?', (folder_id,)).fetchone()
        if not folder:
            raise ValueError('Unknown folder.')
        root = Path(folder['path'])
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Invalid relative file path.')
        source = root / rel
        resolved = source.resolve()
        if not resolved.is_relative_to(root) or resolved.is_relative_to(self.directory):
            return False
        # Windows junctions and symbolic links can point outside the watched folder.
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [source, *source.parents] if p != root.parent):
            return False
        before = source.stat()
        if not source.is_file() or before.st_size > self.max_file_bytes:
            return False
        with source.open('rb') as stream:
            data = stream.read(self.max_file_bytes + 1)
        after = source.stat()
        if len(data) > self.max_file_bytes or (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            return False
        digest = hashlib.sha256(data).hexdigest()
        compressed = zlib.compress(data)
        with self.lock, self.db:
            self.db.execute('INSERT INTO files(folder_id,path) VALUES(?,?) ON CONFLICT DO NOTHING', (folder_id, rel.as_posix()))
            file = self.db.execute('SELECT * FROM files WHERE folder_id=? AND path=?', (folder_id, rel.as_posix())).fetchone()
            if file['current_hash'] == digest and not file['deleted']:
                return False
            self.db.execute('INSERT INTO blobs VALUES(?,?,?) ON CONFLICT DO NOTHING', (digest, compressed, len(data)))
            self.db.execute('INSERT INTO versions(file_id,hash,created,size) VALUES(?,?,?,?)', (file['id'], digest, time.time(), len(data)))
            self.db.execute('UPDATE files SET current_hash=?,deleted=0 WHERE id=?', (digest, file['id']))
            self._prune()
        return True

    def _prune(self):
        self.db.execute('''DELETE FROM versions WHERE id IN (
            SELECT id FROM (SELECT id,ROW_NUMBER() OVER(PARTITION BY file_id ORDER BY id DESC) AS n FROM versions) WHERE n>?)''', (self.versions_per_file,))
        self._collect()
        while self.db.execute('SELECT COALESCE(SUM(length(data)),0) FROM blobs').fetchone()[0] > self.max_storage_bytes:
            row = self.db.execute('SELECT id FROM versions ORDER BY id LIMIT 1').fetchone()
            if not row:
                break
            self.db.execute('DELETE FROM versions WHERE id=?', (row[0],))
            self._collect()

    def _collect(self):
        self.db.execute('DELETE FROM blobs WHERE hash NOT IN (SELECT hash FROM versions)')

    def scan(self):
        """Poll active folders. Never mark files deleted after an incomplete walk."""
        saved, errors = 0, []
        for folder in self.folders():
            if not folder['active']:
                continue
            root = Path(folder['path'])
            if not root.is_dir():
                errors.append(f"Folder unavailable: {root}")
                continue
            seen, incomplete = set(), []
            for parent, dirs, names in os.walk(root, followlinks=False, onerror=incomplete.append):
                parent = Path(parent)
                dirs[:] = [d for d in dirs if d not in EXCLUDED and not (parent/d).is_symlink() and not (hasattr(Path, 'is_junction') and (parent/d).is_junction()) and not (parent/d).resolve().is_relative_to(self.directory)]
                for name in names:
                    path = parent/name
                    relative = path.relative_to(root).as_posix()
                    if name.startswith('.fileback-') or '.recovered-' in name:
                        continue
                    seen.add(relative)
                    try:
                        saved += int(self.capture(folder['id'], relative))
                    except OSError as error:
                        incomplete.append(error)
            if incomplete:
                errors.append(f"Some files could not be read in {root}: {incomplete[0]}")
            else:
                with self.lock, self.db:
                    for file in self.db.execute('SELECT id,path FROM files WHERE folder_id=? AND deleted=0', (folder['id'],)).fetchall():
                        if file['path'] not in seen:
                            self.db.execute('UPDATE files SET deleted=1 WHERE id=?', (file['id'],))
        return saved, errors

    def files(self, search=''):
        with self.lock:
            rows = self.db.execute('''SELECT files.*,folders.path AS folder_path,COUNT(versions.id) AS versions,MAX(versions.created) AS latest
                FROM files JOIN folders ON folders.id=files.folder_id JOIN versions ON versions.file_id=files.id
                GROUP BY files.id ORDER BY latest DESC''').fetchall()
            return [dict(r) for r in rows if search.casefold() in r['path'].casefold()]

    def versions(self, file_id):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM versions WHERE file_id=? ORDER BY id DESC', (file_id,))]

    def content(self, version_id):
        with self.lock:
            row = self.db.execute('SELECT blobs.* FROM versions JOIN blobs ON blobs.hash=versions.hash WHERE versions.id=?', (version_id,)).fetchone()
            if not row:
                raise ValueError('This version is no longer in history. Refresh the list.')
            if not isinstance(row['size'], int) or not 0 <= row['size'] <= self.max_file_bytes:
                raise ValueError('This saved version has an invalid size. Recovery stopped.')
            try:
                decoder = zlib.decompressobj()
                # Do not let damaged or modified history expand without a limit.
                data = decoder.decompress(row['data'], row['size'] + 1)
            except zlib.error as error:
                raise ValueError('This saved version is damaged. Recovery stopped.') from error
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['hash']:
                raise ValueError('This saved version failed its integrity check. Recovery stopped.')
            return data

    def restore_copy(self, version_id, destination):
        """Exclusive creation means even a racing write cannot overwrite a file."""
        data = self.content(version_id)
        destination = Path(destination)
        with destination.open('xb') as stream:
            try:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.close()
                destination.unlink(missing_ok=True)
                raise
        return destination

    def stats(self):
        with self.lock:
            return dict(self.db.execute('''SELECT (SELECT COUNT(*) FROM versions) AS versions,
                (SELECT COUNT(DISTINCT file_id) FROM versions) AS files,
                (SELECT COALESCE(SUM(length(data)),0) FROM blobs) AS bytes''').fetchone())
