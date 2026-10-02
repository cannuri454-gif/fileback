"""Optional fictional-file check; never selects user folders."""
from pathlib import Path
import random
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fileback.store import Store

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    docs = base / 'documents'
    docs.mkdir()
    rng = random.Random(712)
    expected = {}
    for index in range(1000):
        name = f'{index:04d}.bin'
        expected[name] = rng.randbytes(2048)
        (docs / name).write_bytes(expected[name])
    store = Store(base / 'vault', max_storage_bytes=10 * 1024**2)
    try:
        store.add_folder(docs)
        started = time.monotonic()
        with patch('socket.socket.connect', side_effect=RuntimeError('Unexpected network connection')):
            saved, errors = store.scan()
        if saved != 1000 or errors:
            raise RuntimeError('Large-folder scan failed.')
        for file in store.files():
            if store.content(store.versions(file['id'])[0]['id']) != expected[file['path']]:
                raise RuntimeError('Recovered bytes did not match.')
        if store.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Database integrity check failed.')
        print(f'Passed capture and byte verification of 1,000 files ({time.monotonic()-started:.2f}s).')
    finally:
        store.close()
