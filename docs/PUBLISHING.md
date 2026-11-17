# Publishing PeterPiper on GitHub

A step-by-step for putting this repository on GitHub, making a release people can
download, and getting a DOI to cite. Nothing here needs to be done in code.

## What the repository already has

- **The program**: `app/` (Python package `peterpiper`), `PeterPiperV1.2.bat` (launcher and
  installer), `build/` (zip builder, manual builder, `set_github.py`).
- **Every validation test**: `dev_tests/` (see `CONTRIBUTING.md`).
- **Documentation**: `README.md` (the full manual; GitHub shows it on the front page),
  `README.html` (the same, for the zip), `READ ME.txt` (quick start), `CHANGELOG.md`
  (every version and every commit since V2.2).
- **For papers**: `CITATION.cff` (GitHub's *Cite this repository* button), `LICENSE` (MIT,
  Copyright (c) 2026 Peter DePaola IV).
- **GitHub extras**: `.github/ISSUE_TEMPLATE/` (bug report asks for the version and the
  Computer check; feature request), `.gitattributes` (binary files, line endings),
  `.gitignore` (test output, scratch and releases are never uploaded).
- **No microscopy data**: `dev_tests/` only names the lab's test movies by path.

## Before you upload

1. **Your e-mail is in every commit** (as the author). A public repository shows it. To hide
   it in future commits: GitHub > Settings > Emails > *Keep my email addresses private*, then
   `git config user.email <your-id>+<user>@users.noreply.github.com`.
2. **Decide public or private.** Private can be made public later.
3. **The Prism template** (`app/peterpiper/templates/PeterPiper_timecourse.prism`) holds only the
   graph look, no data.

## Upload

**A - GitHub Desktop (no command line)**

1. github.com > **New repository**: name `PeterPiper`; do **not** add a README, license or
   .gitignore (they are here already).
2. GitHub Desktop > **File > Add local repository...** > this folder > **Publish repository**.

**B - command line** (create the empty repository on github.com first)

```
git branch -M main
git remote add origin https://github.com/<your-account>/PeterPiper.git
git push -u origin main
```

With the GitHub CLI: `gh repo create PeterPiper --public --source . --push`.

## Fill in the address everywhere (one command)

```
python build/set_github.py https://github.com/<your-account>/PeterPiper
python build/md2html.py README.md README.html
git commit -am "Project address" && git push
```

This puts the address in Help > About PeterPiper, `CITATION.cff`, the manual's citation
(section 11.5) and `READ ME.txt`.

## Make a release (what people download)

1. Build and check the zip: `python build/build_zip.py --out release --unzip release`
   (it says "byte-identical to the repository" when the zip matches the code).
2. GitHub > **Releases > Draft a new release**: tag `v1.2.1`, title `PeterPiper 1.2`, paste the
   PeterPiper 1.2.0 part of `CHANGELOG.md`, attach `release\PeterPiperV1.2.zip`, **Publish**.
   The Mac workflow (`.github/workflows/mac-app.yml`) attaches
   `PeterPiper-1.2.1-macOS-AppleChip.dmg` and `PeterPiper-1.2.1-macOS-Intel.dmg`.
   *Check for updates* in the program reads this release list (the newest release's tag,
   notes and these files), so keep the file names in this form.
3. Users download the zip from the release page, extract it and double-click
   `PeterPiperV1.2.bat` (`READ ME.txt` says the rest).

## Get a DOI for papers (recommended)

1. zenodo.org > log in with GitHub > *GitHub* > switch the repository **on**.
2. Make the release (above). Zenodo archives it and gives a DOI (e.g. `10.5281/zenodo.1234567`).
3. `python build/set_github.py https://github.com/<your-account>/PeterPiper --doi <the DOI>`,
   rebuild the manual, commit and push. Cite the DOI and name the version.

## Each new version

1. Copy the folder to `PeterPiperV1.x`, set `__version__` / `APP_NAME` in
   `app/peterpiper/__init__.py`, rename the `.bat`, update `CITATION.cff` (version, date).
   Leave `app/requirements.txt` and `app/requirements-compatible.txt` byte for byte as they
   are (header lines included) unless the packages change: the launcher reuses an earlier
   version's install only when its package list is byte-identical (manual, section 3.2).
   Add the previous version's install folder to the front of the launcher's reuse list.
2. Make the changes; run the tests (`CONTRIBUTING.md`); update the manual's version history
   and validation; `python _work/changelog.py` (or write the CHANGELOG entry by hand).
3. Commit, push, release as above. User profiles live in `%USERPROFILE%\PeterPiper data`, so every
   version finds them.
