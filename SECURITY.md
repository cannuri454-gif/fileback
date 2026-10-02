# Security and release status

Fileback v0.1 is an early open-source desktop project. It is not a security product or a replacement for an independent backup.

## Checks performed on 2 October 2026

See the [release verification report](docs/release-verification.md) for test scope, scan evidence, exact download hashes and remaining limits.

- Reviewed the application source for network calls, command execution, credential handling, file-path boundaries, and recovery behavior. The app has no network or shell-execution code and no third-party runtime dependencies.
- Bandit 1.9.4 scanned the application package and launcher: no issues identified, with no suppressed checks.
- pip-audit 2.10.1 checked the installed build packages listed in `docs/build-dependencies.txt`: no known vulnerabilities found at the time of the check.
- 43 automated tests: 42 passed and 1 Windows symlink integration test was skipped because this account could not create symlinks. A separate unit test exercises the symlink guard without elevated permissions. A real Windows junction integration test passed.
- New regression tests cover concurrent capture, transaction rollback after a forced process exit, failed recovery cleanup, Unicode/SQL-like filenames, storage eviction, and open-handle path checks. Capture and text comparison share the same bounded read checks.
- Tests check refusal to overwrite existing files, content-hash verification, corrupt compressed content, invalid metadata sizes, and a limit on decompression output.
- A packaged build was opened and used to recover an earlier demo draft. Its bytes matched the saved version and the current file remained unchanged. A later source hardening change added bounded decompression and was covered by automated tests.

These results are limited checks, not a guarantee that the software has no vulnerabilities. Python itself, bundled system libraries, and every possible hostile filesystem race have not been exhaustively audited.

## Antivirus and signatures

Earlier scan attempts failed with `0x80508023`. A new Microsoft Defender custom scan of the rebuilt executable completed on 2 October 2026, with matching scan-start and scan-finish events and no matching threat detection. The tested artifact's SHA-256 is recorded in the release verification report. This result applies only to those bytes and that scanner's definitions; it does not prove the absence of malware or vulnerabilities.

The executable is unsigned. There is no claim of a trusted publisher identity or established Windows download reputation. A new build has a new file hash and must be scanned separately. Do not disable antivirus or Windows security settings to use this project.

No executable has been uploaded to a third-party malware-scanning service in this review. The repository publishes the source, documentation, and a build workflow. Workflow artifacts are unsigned development builds, not a reviewed stable release.

## What is protected

- Only folders the user selects are scanned.
- Reads outside the stored folder root and reads of the history vault are rejected.
- Symlinks and Windows junctions are skipped. Windows reads also verify the actual open handle's path and file identity before reading. Hard links inside a selected folder can still refer to shared file content. This is not a hostile-filesystem sandbox: another process running as your user can still modify files or the history database.
- Recovery verifies saved file size and SHA-256 and limits decompression output.
- Recovery creates a new destination exclusively. An existing file cannot be overwritten by this operation.
- Database writes use SQLite transactions. SQL values are passed as parameters.

## What is not protected

- The local history database is not encrypted or authenticated. Anyone with access to your Windows account or those files may read or modify it. A SHA-256 check detects mismatches; it does not prove who wrote the database.
- A protected folder may contain passwords, tokens, or other private files. Old copies can remain after the source is deleted. Select folders with that in mind.
- There is no anti-ransomware, secure deletion, remote backup, or disk-failure protection.
- Do not open history databases obtained from other people. Importing arbitrary history is not a supported feature.
- Retention removes old versions, polling may miss quick changes, and watching stops when the app closes.

## Reporting a problem

For a reproducible non-sensitive bug, open a repository issue using fictional files. Never attach personal history databases, passwords, or private file contents to a public issue. If GitHub private vulnerability reporting is available on the repository, use it for sensitive findings.

## Before a stable downloadable release

- Complete antivirus checks on the exact release artifact and record the result and hash.
- Review signing and distribution options; signing alone does not guarantee no reputation warnings.
- Broaden Windows testing to different machines, very large folders and real power-loss behavior. Tests cover a junction, 1,000 files, and a forced process exit during an uncommitted transaction; that is not a physical power-loss test.
- Add user settings and clearer visibility into skipped files and retention.
- Obtain independent review and real-user testing.
