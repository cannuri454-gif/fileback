# Third-party software

Fileback source is MIT licensed. The Windows executable also contains unmodified Python, Tcl/Tk, SQLite, zlib and the PyInstaller bootloader. Those components retain their own licenses; the app's MIT license does not replace their terms.

The Windows ZIP includes Python's complete license notice, the installed Tk notice, the corresponding Tcl notice, and PyInstaller's license with its bootloader distribution exception. SQLite is public domain; zlib uses its permissive upstream license. Preserve all notices when redistributing the executable.

The checked local build uses Python 3.14.3 and PyInstaller 6.20.0. Source builds and workflow builds may use a different Python patch release. Check the exact runtime and dependency versions before redistributing a changed build.

Upstream projects and license details:

- Python: https://docs.python.org/3/license.html
- Tcl/Tk: https://www.tcl.tk/software/tcltk/license.html
- SQLite: https://www.sqlite.org/copyright.html
- zlib: https://zlib.net/zlib_license.html
- PyInstaller: https://pyinstaller.org/en/stable/license.html
