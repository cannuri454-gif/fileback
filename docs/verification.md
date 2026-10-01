# Local verification

Verified on Windows 11 with Python 3.14.3 on 2 October 2026.

- `python -m unittest discover -s tests -v`: 24 tests discovered; 23 passed, 1 skipped because this Windows account could not create a symbolic link.
- The desktop tests use real Tk widgets and the background worker. They check previews, comparisons, pause/resume, search, recovery, and a real file edit.
- Built a standalone Windows x64 executable with PyInstaller 6.20.0.
- Opened the executable, selected an earlier draft, compared it with the current file, and recovered it through the native save dialog.
- Checked that the recovered file matched the saved bytes exactly and that the current file remained unchanged.
- Reviewed the packaged desktop layout and saved the screenshot in this folder. The files in that screenshot are fictional demo files.

See the repository Actions page for remote workflow results. Cross-platform behavior, very large folders, power-loss recovery, and Windows junction exclusion have not been integration-tested in this session. See [SECURITY.md](../SECURITY.md) for the security checks and the unsuccessful antivirus scan attempt.
