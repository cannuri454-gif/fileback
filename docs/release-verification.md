# Release verification: ModelCheck and Fileback

Checked on Windows 11 on 2 October 2026. These are alpha previews, not certified or bug-free products. Use the latest preview rather than the earlier ModelCheck download.

## Results

| Check | ModelCheck | Fileback |
| --- | --- | --- |
| Automated tests | 59 passed | 41 passed, 1 skipped |
| Combined statement/branch coverage | 90% | 83% |
| Core evaluation/storage coverage | 93% | 91% |
| Bandit application-source scan | No flagged issues, no suppressed checks | No flagged issues, no suppressed checks |
| pip-audit of declared runtime/build/test requirements | No known vulnerabilities found at check time | No known vulnerabilities found at check time |
| pip dependency consistency | Passed | Passed |
| Built Windows app `--self-test` | Exit code 0 | Exit code 0 |
| Freshly extracted download ZIP `--self-test` | Exit code 0 | Exit code 0 |
| ZIP integrity and extraction-path checks | Passed | Passed |
| Microsoft Defender custom scans | Full application folder and final ZIP completed; no matching threat detection | Executable and final ZIP completed; no matching threat detection |
| Digital signature | Unsigned | Unsigned |

Coverage.py 7.16.2 measures exercised statements and branches together. Coverage does not measure every possible input, fault or user action. The skipped Fileback test needed permission to create a symbolic link; the separate link-guard unit test and real Windows junction test passed. No security settings were weakened or bypassed.

## Bugs fixed

**Fileback:** text comparison now uses the same bounded, checked read as capture. Windows reads check the actual open file handle's path and file identity. Drive-relative, outside-root and alternate-stream paths are rejected. A changed root/junction cannot be treated as a completed scan. A file whose saved content was removed by the storage budget can be saved again without requiring an edit.

**ModelCheck:** report exports refuse the loaded CSV, history database and existing aliases of those files, and allow only HTML/JSON names. Reports are written to a flushed temporary file before replacing the destination; a failed write preserves the old report. CSV null bytes, numeric timestamp guesses, duplicate models and extreme feature values are rejected. Categorical preprocessing remains sparse. Columns named `(none)` are handled correctly. A result already queued when cancellation is requested is not saved afterward.

## Failure and security cases tested

- Fileback: concurrent capture, unchanged/same-size edits, deleted/recreated files, unavailable folders, incomplete scans, pause/resume, binary and empty files, safe recovery, refusal to overwrite, damaged/truncated/oversized compressed content, invalid sizes, SQL-like and Unicode filenames, link/junction exclusion, path escapes, retention cleanup, failed writes, transaction rollback after an abrupt process exit, UI errors and clean worker shutdown.
- ModelCheck: correct metrics on known predictions, training-only preprocessing, repeatable splits, split membership and group/date boundaries, tied dates, edge seeds/fractions, missing labels/groups/features, unknown categories, category/row/column/byte limits, extreme numbers, invalid dates, invalid UTF-8, BOM, quoting/multiline CSV, HTML injection attempts, escaped reports, damaged JSON history, failed history saves, protected/atomic exports, cancellation races, closing during work, settings restoration and rendering at a smaller window size.
- 300 deterministic random-byte CSV cases were rejected without an unexpected exception.
- A fictional 50,000-row/eight-feature ModelCheck dataset completed logistic regression and random forest in about six seconds. This does not test the simultaneous 200-column/100-MB worst case.
- Fileback saved 1,000 fictional 2-KB files and verified every recovered byte in about 23 seconds. A separate automated test covers 250 files.
- The stress runs blocked socket connections and completed successfully. Source review found no application network calls, user-code execution, credential handling or imported pickle/joblib models. This is not a full network audit of every OS/library code path.
- A repository scan found no matches for common GitHub-token and private-key patterns. This is not a scan of every possible secret format.

## Antivirus evidence

Microsoft Defender was enabled with real-time protection. Definitions: **1.459.509.0**, updated 1 October 2026. No configured path exclusion matched either release location; archive scanning was enabled. Custom scan-start (event 1000) and scan-finish (event 1001) pairs were checked for:

| Artifact | Defender scan ID |
| --- | --- |
| Fileback.exe | 99329365-E5E9-4D63-8719-AA49198D0F98 |
| ModelCheck application folder | AB7EE5AE-1760-4672-8CD4-85C60B5A66FF |
| Fileback-Windows.zip | 4F15F5E6-CC11-4651-9D83-172C4404D12E |
| ModelCheck-Windows.zip | F8CF973C-DE89-4880-B699-5144A23DD081 |

Earlier Fileback scan attempts failed; the new scans above completed. No matching detection was returned by Defender's threat-detection history. A completed scan with no detection is limited evidence from one engine and one set of definitions, not proof that a file is safe. No VirusTotal/multiple-engine scan or independent penetration test was performed. No private user data or history database was submitted to an external scanner.

## Exact checked bytes

SHA-256 identifies the checked files. Compare your download with the published checksum; a matching hash confirms the bytes, not safety.

- `Fileback.exe`: `fae9e39d2826f34a0d5cf1565586407718ba49dabda1e24f3d74b43f806f647a`
- `Fileback-Windows.zip`: `a39cddc8c8e9d4124170bb28895ca22862455646e854e94df8f98dcd90beac67`
- `ModelCheck-Windows.zip`: `f3fe7baf64cfe677119c9c8f3a79e37e120d96435870b387ec2d57e90678999b`
- `modelcheck-windows/ModelCheck/ModelCheck.exe`: `82ab3555ff8954ac22765376a1852bb90821282fc32f19af7db0890be7b7a615`

## Remaining limits

- Both apps remain unsigned alpha software. Windows may show an unknown-publisher/reputation warning. Never disable protection to run them.
- Local history and exported reports are unencrypted. Fileback can preserve deleted secrets; ModelCheck reports can expose column names, labels and group identifiers. Only select data you are allowed to use, and avoid publishing private data.
- Fileback is local file history, not an independent backup or ransomware protection. Polling can miss fast changes. A local same-account attacker can still alter the filesystem or database. Hard links can share file content with paths outside a selected folder.
- ModelCheck supports binary classification and fixed models with one holdout per method. A clean result does not prove no data leakage, fairness or readiness for deployment. Repeated observations can make its accuracy interval too narrow.
- Native Python/Qt/numerical libraries and the operating system were not exhaustively audited. Package audits do not cover all interpreter/native-library vulnerabilities. Other machines, physical power loss, long endurance runs, screen readers and the simultaneous largest allowed input have not been validated.
- Independent security review and real-user testing are still needed before describing either app as a stable release. No set of automated checks can establish zero bugs or zero risk.

## Repeating the checks

Use the repository's pinned requirements and Windows workflow. Local verification uses `python -m coverage run --branch --source=modelcheck -m pytest -q` for ModelCheck and `python -m coverage run --branch --source=fileback -m unittest discover -s tests -v` for Fileback. Run Bandit on the app package and launcher, pip-audit on the declared requirements, and `--self-test` on each exact built executable. Scan and hash every rebuilt archive separately. The repository workflow builds a different artifact on a different machine; local scan results do not automatically apply to that workflow artifact.
