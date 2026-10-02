# Local verification

Verified on Windows 11 with Python 3.14.3 on 2 October 2026.

- `python -m unittest discover -s tests -v`: 43 tests discovered; 42 passed, 1 skipped because this Windows account could not create a symbolic link. The Windows junction test passed.
- Coverage.py 7.16.2 measured 83% combined statement/branch coverage across the application, including 91% in storage. Coverage is a measurement, not proof of correctness.
- Additional tests cover path and alternate-stream rejection, checked open handles, concurrent capture, damaged compressed content, incomplete/failed writes, retained-content eviction, SQL-like names and transactional recovery after abrupt process exit.
- Saved and verified every byte in 1,000 fictional 2 KB files. The local run took about 23 seconds while other release checks were running; this is a smoke benchmark, not a performance guarantee.
- The desktop tests use real Tk widgets and the background worker. They check previews, comparisons, pause/resume, search, recovery, and a real file edit.
- Built a standalone Windows x64 executable with PyInstaller 6.20.0.
- Opened the executable, selected an earlier draft, compared it with the current file, and recovered it through the native save dialog.
- Checked that the recovered file matched the saved bytes exactly and that the current file remained unchanged.
- Reviewed the packaged desktop layout and saved the screenshot in this folder. The files in that screenshot are fictional demo files.

See the repository Actions page for remote workflow results. Real power-loss recovery, other operating systems and every possible hostile filesystem race have not been validated. See [SECURITY.md](../SECURITY.md) and the release verification report for security checks and exact download hashes.
