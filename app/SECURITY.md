# PeterPiperV2.3 - security and data safety

(Called `SECURITY_CHANGES.md` up to V2.2.)

## In short

- **Everything runs on your computer.** The app has no network code: it does not
  upload images, results, settings or usage data anywhere. The internet is used
  once, by `PeterPiperV2.3.bat`, to download the Python packages listed in
  `requirements.txt` from the official Python package index (https://pypi.org).
- **Exact package versions.** `requirements.txt` pins every package, including
  the packages those packages need, to the exact version the app was tested
  with (`==`), so every install gets the same code. Only if a computer cannot
  install those versions (for example Python 3.10) does the installer fall back
  to the version ranges in `requirements-compatible.txt`, and it says so on
  screen. Either way the versions really installed are written to
  `%USERPROFILE%\.PD4navV2.3\venv\installed_versions.txt`.
- **Your files are never replaced.** Exports (Excel, PNG, Prism, TIFF, ROI files)
  are always new files, created exclusively, with a number added to the name
  if the name is taken. The one file the app replaces is its OWN current session
  file (the automatic save of the session you have open, in
  `PD4nav_sessions` next to the results); it is written to a temporary file
  first and then swapped in, so it is never left half-written.

## What the installer does (`PeterPiperV2.3.bat`)

- Makes a private Python environment in `%USERPROFILE%\.PD4navV2.3\venv`
  (or in `%PETERPIPER_HOME%\venv` when that variable is set). Nothing is installed
  into the system Python.
- Clears inherited `PIP_*` settings and ignores pip configuration files
  (`PIP_CONFIG_FILE=nul`), uses the https PyPI index explicitly, accepts
  ready-made packages (wheels) only - nothing is built from source code - and
  refuses to install outside the private environment (`--require-virtualenv`).
- Never upgrades pip, setuptools or wheel by itself.
- Reuses the install of PeterPiperV2.2 or V2.1 only when that install was made from
  a byte-identical package list.
- Keeps a copy of the package list it installed (`installed_requirements.txt`);
  when the list in the app folder changes, it installs again.
- If antivirus shows an alert, stop and check it with IT; do not allowlist the
  folder.

## What the app reads and writes

- Reads the .nd2 / ROI files you choose.
- Writes results into the output folder you choose (by default `OUTPUT_<name>`
  next to the .nd2 file), including its session files in `PD4nav_sessions`.
- Keeps its settings and a list of earlier runs (file names, paths, sizes and a
  fingerprint of each .nd2 file - no image data) in `%USERPROFILE%\.PD4navV2.3`.
- ROI files are NumPy archives read with `allow_pickle=False` (no code can be
  loaded from them).

## Hardening kept from the V2.2 security revision

- Exported settings strings are forced to literal Excel text, so a leading `=`
  never becomes a formula; apostrophes in generated sheet-name tags are replaced.
  Intentional analysis formulas are unchanged.
- Export file names are checked for path separators, characters Windows does not
  allow, control characters, reserved Windows names and trailing spaces/periods;
  the TIFF subfolder must stay inside the chosen output folder.
- Workbook names include the time to the microsecond; the save dialog reports
  the actual file name.
- Cancelling an export does not claim that nothing was written: finished or
  partial NEW files can remain (old files are never touched).

## Limits

- The downloaded packages are pinned by version, not by hash, and were not
  audited for vulnerabilities; the download source is restricted to https PyPI
  and source builds are refused, which reduces but does not remove that risk.
- A virtual environment is not a security sandbox: the app can read and write
  wherever your Windows account can. Use trusted input files and a dedicated
  output folder.
- Failed or cancelled writes may leave partial new files; they never replace
  existing ones.
