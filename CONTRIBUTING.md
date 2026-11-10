# Contributing to PeterPiper

Thank you for helping. PeterPiper is used to make numbers that go into papers, so every
change keeps three rules: **measurements come from the raw pixels**, **every number can be
traced to a documented formula** (the manual, section 8), and **nothing a user saved is
overwritten or deleted**.

## Reporting a problem

Open an issue with the *Bug report* template. Please include the PeterPiper version (window
title), what *Help > Computer check...* shows, and the steps that lead to it. **Do not attach
unpublished images or data**; a description, a screenshot or a methods text is usually
enough.

## Setting up

Windows 10 / 11, 64-bit Python 3.11 - 3.14. The launcher (`PeterPiperV1.0.bat`) installs the
exact package versions in `app/requirements.txt` into a private environment; for development
use that environment's Python (`%USERPROFILE%\.PD4navV3.0\venv\Scripts\python.exe`) or a
virtual environment with the same requirements.

## Tests

Every validation test is in `dev_tests/` (developer tests, not shipped in the zip). Run them
all, offscreen, with:

```
python dev_tests/run_tests.py            (or: python dev_tests/run_tests.py v29 graph)
```

It prints PASS / FAIL / SKIPPED per test (logs in `_out/tests/`).

- **A small synthetic movie ships with the code** (`dev_tests/data/synthetic_movie.npz`,
  made by `dev_tests/synthmovie.py`): 16 drifting nuclei, a GFP sensor in half of them with a
  known 2-fold rise, untransfected cells and an empty strip for the background. `test_v29.py`
  checks PeterPiper's numbers against these known answers.
- Tests that need the lab's own `.nd2` movies (unpublished data, not shipped) say
  **SKIPPED - lab data only** without them (`dev_tests/labdata.py`) - not a failure.
  The tests never name those files: they ask `labdata.T("t07")` and the lab's own
  computers keep the names in `dev_tests/lab_paths.json` (or `$PETERPIPER_LAB_PATHS`),
  which git ignores - never commit it, and never write a lab file's name or folder
  into a test.
- Each test writes only to `_out/` in the repository and uses its own settings folder
  (`PETERPIPER_HOME`), so it never touches your own settings or data. Movies are only read.
- Tests that drive GraphPad Prism (`test_prism_live.py`, `test_prism_style.py`) need Prism 11.
- Any modal dialog a test opens must be answered (stubbed) in the test, or it waits forever.

## Code

- `app/peterpiper/` - the measurements and files (`measure.py`, `manual.py`, `export.py`, ...);
  `app/peterpiper/gui/` - the windows. The code map is in `app/README.md` and the manual
  (section 16).
- Keep changes small and documented: a user-visible change updates the manual (`README.md`),
  the quick start (`READ ME.txt`) where relevant, and the version history.
- `python build/md2html.py README.md README.html` rebuilds the HTML manual;
  `python build/build_zip.py --out release --unzip release` builds the zip users download.

## License

By contributing you agree that your contributions are released under the MIT License
(`LICENSE`).
