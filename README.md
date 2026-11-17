# PeterPiper - single-cell fluorescence time courses from Nikon .nd2 movies

**Free and open source (MIT) · Windows 10 / 11 and macOS 14+ · runs entirely on your own computer.**
By Peter DePaola IV, Schmitt Lab, University of California, Los Angeles.

PeterPiper was called **PD4nav** up to version 3.0. **PeterPiper 1.0 continues PD4nav V3.0**: the same methods and the same numbers, a new name and logo, and a fresh start on every computer (section 15). **PeterPiper 1.1** keeps the same methods and the same numbers and adds a redesigned start screen and analysis window, a movie queue with SAVE and *Next movie*, *Smart auto-select* (cell selection learned from your own hand-picked movies), profiles kept in step between computers and across a lab, results and back-ups in cloud folders, colour-blind-safe cell colours and an optional *Check for updates* (section 15). **PeterPiper 1.2** keeps the same methods and the same numbers and adds a *Merge* tool for ROIs (two ROIs next to each other that are one cell become one), a choice of the folder each export goes into with help for paths that are too long for Windows, loading bars that show the percent, the time left and what is being read, a launcher that reuses an identical earlier install and says what it is doing while it installs, and the offer to take in ("absorb") older PeterPiper versions left on the computer (section 15). Version tags such as *(V2.9)*, *(V3.0)*, *(1.1)* or *(1.2)* in this manual mark the version a feature arrived in.

**What it does**

- You click on cells in a Nikon NIS-Elements `.nd2` time-lapse movie (or let AUTO-DETECT propose them); PeterPiper draws each region of interest from the image and **follows every cell through every timepoint**, redrawing it from that timepoint's pixels.
- It **measures every channel in every cell** from the raw pixels, subtracts a background measured at every timepoint, and gives intensities, ratios, F/F0 and R/R0 - with a check that leaves out divisions by almost nothing.
- It **exports** Excel workbooks (live formulas), GraphPad Prism files with the graph already made, CSV tables, graphs, ROI pictures and a **ready-to-edit methods text** with every value used.
- Saved runs can be **compared and averaged as replicate dishes** (mean of dish means, n = dishes), with kinetics (t½, initial slope).
- Several movies can be analysed **one after another as a queue**; after a few movies picked by hand, **Smart auto-select** picks cells on new movies of the same kind the way you do (section 6.15).

**Download and install** - from the project's **Releases** page (https://github.com/peterdepaola4/PeterPiper/releases)

*Windows 10 / 11:*

1. Download `PeterPiperV1.2.zip`.
2. Right-click it > *Extract All...* into a simple local folder (not OneDrive or a network drive).
3. Double-click **`PeterPiperV1.2.bat`**. The first time on a computer it installs its own private Python packages into `%USERPROFILE%\.PeterPiperV1.2` (about 2 - 5 minutes, internet once); where PeterPiper 1.1 or 1.0 is already installed with the same packages, it uses that install and opens at once. After that it opens straight away. It needs 64-bit Python 3.11 - 3.14 from python.org (section 3). Users and runs from PeterPiper 1.0 and 1.1 carry over (they are in `%USERPROFILE%\PeterPiper data`); the start screen then offers to tidy up the older versions (section 3.8).

*macOS 14 (Sonoma) or newer:*

1. Download `PeterPiper-1.2.1-macOS-AppleChip.dmg` (Macs with an Apple M chip) or `PeterPiper-1.2.1-macOS-Intel.dmg` (older Intel Macs; *Apple menu > About This Mac* says which).
2. Open it and drag **PeterPiper** onto **Applications**.
3. Double-click PeterPiper in Applications. Nothing else to install: the app carries its own Python. The first time, macOS says it cannot check PeterPiper for malicious software (PeterPiper is not registered with Apple): click **Done**, open **System Settings > Privacy & Security**, scroll down to *"PeterPiper" was blocked...* and click **Open Anyway**, then **Open** (and your Mac password). From then on it opens with a double-click like any app. (section 3.7)

**Quick start** (section 5 has more)

1. Pick your name (*Who is using PeterPiper?* - each person's data is kept apart).
2. **Analyse movies**: choose one `.nd2` - or several at once, which become your movie queue; check the pixel size and frame interval, *Open in the analysis window*.
3. Check the tracking rule (e.g. *Auto-detect nucleus using Cy5*), click each cell (or AUTO-DETECT), and **pick a background spot** (right-click an empty area).
4. **TRACK & MEASURE**, press Play to check the outlines follow the cells, include / exclude cells.
5. **SAVE** (with an optional note) and **EXPORT**; in a queue, **Next movie**. *Compare / average saved runs* puts dishes together.

**Cite** - name the version you used and keep the exported methods text with your data:
DePaola P IV. PeterPiper: single-cell fluorescence time-course analysis for Nikon .nd2 movies, version 1.2.1 (2026). Schmitt Lab, University of California, Los Angeles. https://github.com/peterdepaola4/PeterPiper - also *Cite this repository* (from `CITATION.cff`) and section 11.

**For developers** - `CONTRIBUTING.md` (tests run on a small synthetic movie shipped with the code), `docs/PUBLISHING.md`, `CHANGELOG.md`; the code map is in section 16.

---

## The manual

**PeterPiper version 1.2.1** (program name `PeterPiperV1.2`; formerly PD4nav, continuing PD4nav V3.0) · Windows 10 / 11, 64-bit, and macOS 14+ · Python 3.11 - 3.14 · runs entirely on your own computer

PeterPiper measures fluorescence in single cells over time in Nikon NIS-Elements `.nd2` time-lapse movies. You click on the cells; PeterPiper draws each region of interest (ROI) from the image, follows every ROI through every timepoint by redrawing it from that timepoint's pixels, measures every channel in every ROI, subtracts a background measured at every timepoint, and exports Excel, GraphPad Prism, CSV, graphs, ROI pictures and a ready-to-edit methods text. Saved runs (dishes) can be compared and averaged as replicates (mean of dish means ± SEM, n = dishes).

This manual explains every step, how every number is made (with the exact parameters in the code), what is written where, and what to report when you use PeterPiper in a scientific paper. For a one-page start, read `READ ME.txt` next to `PeterPiperV1.2.bat`.

**Author:** Peter DePaola IV ([ORCID 0000-0003-4264-0375](https://orcid.org/0000-0003-4264-0375)), Schmitt Lab, UCLA. **License:** MIT (section 17, `LICENSE`). **How to cite:** section 11.5 and `CITATION.cff`. **Changes:** section 15 and `CHANGELOG.md` (every version and every commit).

<!-- toc -->
**Contents**

1. [What PeterPiper is (and what it is not)](#1-what-peterpiper-is-and-what-it-is-not)
2. [System requirements](#2-system-requirements)
3. [Installing](#3-installing)
4. [Privacy: everything runs on your computer](#4-privacy-everything-runs-on-your-computer)
5. [Quick start](#5-quick-start)
6. [The workflow, step by step](#6-the-workflow-step-by-step)
7. [Session memory: your work is kept](#7-session-memory-your-work-is-kept)
8. [How the numbers are made (methods detail)](#8-how-the-numbers-are-made-methods-detail)
9. [Outputs reference](#9-outputs-reference)
10. [Reproducibility](#10-reproducibility)
11. [Using PeterPiper in a paper](#11-using-peterpiper-in-a-paper)
12. [Validation](#12-validation)
13. [Known limitations](#13-known-limitations)
14. [Troubleshooting](#14-troubleshooting)
15. [Version history](#15-version-history)
16. [File and code map](#16-file-and-code-map)
17. [License](#17-license)
<!-- /toc -->

## 1. What PeterPiper is (and what it is not)

PeterPiper is a desktop program (Python, Qt) for **semi-automatic, user-checked single-cell intensity measurement in fluorescence time-lapse movies**:

- **You decide what a cell is.** You click on each cell (or let AUTO-DETECT propose the obvious ones and then review them). PeterPiper draws the outline from the image around your click. ROIs of one cell - nucleus, whole cell, cytoplasm, mitochondria - are linked under one cell number.
- **Every ROI is redrawn at every timepoint.** The tracker measures how each cell moved (sub-pixel phase correlation), moves its ROIs, and re-outlines them from that timepoint's own pixels, with a hard size limit relative to what you drew (0% = exactly the drawn pixel count), no pixel shared between two cells, and optional **tracker boundary** lines a cell's ROIs never cross.
- **Tracking rules** say which channel each kind of ROI is outlined and followed on, and how a second channel is used: `Track [Nucleus / Whole cell / Cytoplasm / Mitochondria] using [channel A] [ONLY / WITH / AND / IF] intensity in [channel B]`. Since V2.5 every rule follows the cell on channel A exactly as ONLY does; the second channel can only remove pixels from that outline (WITH, AND) or exclude cells (IF), never make an ROI bigger.
- **Every channel is measured in every ROI, always**, from the raw full-resolution pixels (ROI mean = sum of the pixel values / number of pixels). The background is measured in a region that may contain non-transfected cells (their autofluorescence is part of the background); every pixel of the region is used at every timepoint (nothing is left out), and after tracking you are told if the background jumps or drifts, so you can redraw it. Background subtraction, F/F0, every channel ratio and R/R0 follow.
- **You check before you export**: play the movie with the outlines on top, look at every cell's trace, include or exclude cells. Automatic quality-control (QC) notes help; they never remove a cell by themselves.
- **Every export records how it was made**: the tracking rules, every tracking parameter, the software versions and a fingerprint of the `.nd2` file, plus a ready-to-edit methods text with references.
- **Your work is kept**: the ROIs and the tracking are saved automatically as you work; when you open a movie analysed before, PeterPiper offers to load the earlier analysis (identical saves are listed once).
- **Replicates are averaged per dish**: the *Compare / average runs* window puts saved runs (one run = one dish) into groups and shows the mean of the dish means ± SEM with n = dishes, plus the pooled cells for reference, with colours chosen by cell line.
- **Selection that learns your judgement** (1.1): *Smart auto-select* is trained on movies in which you picked the cells by hand (kept in named bins, one per kind of experiment), so that automated selection on large data sets follows the researcher's own criteria; how many hand-picked movies it learned from, and its held-out accuracy, go into the methods text of every run that used it (sections 6.15, 8.13).

What PeterPiper is **not**:

- not a fully automatic segmentation pipeline - AUTO-DETECT is deliberately conservative and only proposes clearly visible, well-separated objects, and Smart auto-select only reproduces the selection you made by hand; every proposal is reviewed by you;
- not a lineage tracker - cells are followed, not split or merged; divisions, cells entering or leaving the field are not modelled;
- not a 3-D tool - Z stacks are reduced to a maximum-intensity projection, and one stage position is analysed at a time;
- not a general image reader - it opens Nikon `.nd2` files only;
- not a statistics package - it gives per-cell values, the mean, SD, SEM and 95% confidence interval of the included cells, and the same statistics across dishes (mean of dish means); statistical tests are up to you;
- not validated against a ground-truth segmentation data set - its validation consists of consistency, regression and round-trip tests (section 12).

## 2. System requirements

| What | Requirement |
|---|---|
| Operating system | Windows 10 or Windows 11, 64-bit; or **macOS 14 (Sonoma) or newer** on Apple-chip or Intel Macs (the Mac app, section 3.7). No Linux launcher. |
| Python | Windows: 64-bit Python **3.11, 3.12, 3.13 or 3.14** from python.org, installed with "Add python.exe to PATH" ticked. Python 3.10 also works, but gets compatible package versions instead of the exact tested ones (the launcher says so). Python 3.9 and older are not accepted. Mac: none - the app carries its own. |
| Disk space | About 0.5 GB for the private Python environment (the tested install was about 460 MB); keep 1 GB free. Plus space for results (below). |
| Internet | Once, for the first-time install: about 250 MB of packages from the official Python package index (https://pypi.org); not needed when the launcher reuses an identical earlier install (1.2, section 3.2). After that only if you press *Check for updates* (1.1, optional; section 4). |
| Memory (RAM) | See below: 8 GB minimum, 16 GB recommended for large multi-channel movies. |
| Screen | 1.1: the start screen, the analysis window and the Compare window open maximized and are laid out to need no scroll bars on a 1366 x 768 screen at the default text size; larger screens give more room. Text size is adjustable (larger text may need scrolling on small screens). |
| To open the results | Excel or LibreOffice (`.xlsx`, with live formulas); GraphPad Prism 10 or newer for `.prism` files (verified with Prism 11), any Prism version for `.pzfx`; Fiji / ImageJ for the raw TIFFs (optional). |

**Memory guidance.** The `.nd2` file is never loaded whole: frames are read one timepoint at a time (through the `nd2` and `dask` packages), so a 4 GB movie does not need 4 GB of memory. What matters is the size of one timepoint: channels x width x height x 2 bytes (16-bit). For 3 channels of 2400 x 2400 pixels that is about 35 MB. The image display keeps recently viewed timepoints in a cache of at most 1.5 GB (`FrameStore`, `budget_bytes = 1 500 000 000`), and tracking reads up to 4 timepoints ahead. With 8 GB of RAM this works comfortably for typical movies; with 16 GB or more you can keep other programs open. (These are recommendations from the code's memory budget, not measured limits.)

**Disk space for results.** Excel, Prism, CSV and PNG files are small (kilobytes to a few megabytes). An autosaved session file is a few megabytes (3.7 MB for 61 timepoints x 10 mitochondria ROIs). Raw TIFF export is the exception: it writes every timepoint and channel uncompressed, timepoints x channels x width x height x 2 bytes - for example 61 x 3 x 2400 x 2400 x 2 bytes ≈ 2.1 GB.

**Speed.** Opening a large `.nd2` takes a few seconds; reading one 2400 x 2400 frame of a 4 GB file takes about 0.2 - 0.5 s. Tracking time grows with the number of timepoints and ROIs; the window shows an estimate before you start. The background (section 8.4) is a plain sum over the region's pixels at every timepoint and adds almost nothing.

## 3. Installing

### 3.1 Step by step

1. **Python (once per computer).** If Python is not installed: go to https://www.python.org/downloads/windows/, download Python 3.13 (or 3.12 / 3.11), "Windows installer (64-bit)", run it and **tick "Add python.exe to PATH" on the first screen**. (A Python from the Microsoft Store also works; it was found and used in the install test.)
2. **Unpack.** Copy `PeterPiperV1.2.zip` to the computer, right-click it, choose **Extract All...** and pick a simple local folder such as `D:\PeterPiperV1.2`. Not OneDrive, not a network drive, and never run it from inside the zip.
3. **Start.** Open the extracted folder and double-click **`PeterPiperV1.2.bat`** - the only file you ever open. **Where PeterPiper 1.1 or 1.0 is already installed** with the same package list, the launcher uses that install (1.2, section 3.2, step 4) and the program opens at once. **Otherwise, the first time on a computer**, a black window shows "PeterPiper 1.2 - first-time setup": `[1/3] Setting up a private Python` (about 10 - 30 s), `[2/3] Downloading packages` (about 250 MB; whenever pip prints nothing for 5 s, a line `still working - ...` says what it is doing, how long it has taken and roughly how long is left), `[3/3] Checking that every package loads` (`checking numpy ... OK  (1 of 14)` ... `all packages OK`), "Setup finished". This takes about 2 - 5 minutes (132 s in the 1.2 test, 250 s in the V2.3 test). Then the program opens; this first start takes about 10 - 20 seconds and the window says so.
4. **Every later time** the launcher checks the install (a fraction of a second), says "Starting PeterPiper - the window opens in a few seconds." and opens the program, without internet.
5. **Older versions** (1.2): if older PeterPiper versions (1.0 or later) are found on the computer, the start screen offers once per start to take them in - their shortcuts then start 1.2, and their program files and private Python go to the Recycle Bin, from where they can be restored (section 3.8). *Not now* and *Don't ask again for these* leave them as they are.

What is in the zip:

| File / folder | What it is |
|---|---|
| `PeterPiperV1.2.bat` | The launcher: installs on first use, then starts the program. |
| `READ ME.txt` | One-page quick start. |
| `README.html`, `README.md` | This manual (the same text; the `.html` opens in any browser). |
| `app\PeterPiper.py` | The program's start file (called by the launcher). |
| `app\peterpiper\` | The program code (Python package `peterpiper`), including `templates\PeterPiper_timecourse.prism` (the Prism graph template) and `templates\PeterPiper_look.json` (the template's look per data set). |
| `app\requirements.txt` | The exact package versions PeterPiperV1.2 was tested with (the same versions as PeterPiper 1.0 and 1.1). |
| `app\requirements-compatible.txt` | The fallback list of version ranges. |
| `app\install_progress.py` | 1.2: what the launcher shows while pip installs and while the packages are checked (Python's standard library only). |
| `app\README.md`, `app\SECURITY.md` | Short code map; security and data-safety notes. |

### 3.2 What the launcher does

`PeterPiperV1.2.bat` is a plain Windows batch file; you can open it in Notepad and read it. In order:

1. **Checks that it was extracted** (`app\PeterPiper.py` and `app\requirements.txt` must exist next to it); otherwise it explains how to extract the zip.
2. **Shows the PeterPiper logo** in its window, drawn with block characters (`app\peterpiper\assets\logo_116.txt`, `logo_100.txt` or `logo_72.txt`: the widest that fits the window), at the first install and at every start.
3. **Chooses the install folder**: `%USERPROFILE%\.PeterPiperV1.2` (for example `C:\Users\you\.PeterPiperV1.2`), or the folder in the environment variable `PETERPIPER_HOME` if set. The private Python environment goes into its `venv` subfolder.
4. **Uses an existing install if it is up to date**: if `venv\installed_requirements.txt` (a copy of the package list it was installed from) is byte-identical to `app\requirements.txt`, the program starts at once. **1.2: an identical earlier install is reused.** When this version has no install of its own yet (and `PETERPIPER_HOME` is not set), the launcher looks in this order at `%USERPROFILE%\.PeterPiperV1.1`, `.PeterPiperV1.0` and then PD4nav's install folders (`.PD4navV3.0` back to `.PD4navV2.1`), and uses the first whose `installed_requirements.txt` is byte-identical to `app\requirements.txt` and whose Python still starts (its base Python may have been uninstalled since). PeterPiper 1.2's package list is the same as 1.1's, so on a computer with PeterPiper 1.1 it opens at once, without downloading anything. The install it uses is not copied or changed; its `installed_versions.txt` is the one that applies (section 10).
5. **Otherwise installs.** It looks for 64-bit Python in this order: `py -3.11`, `py -3.12`, `py -3.13`, `py -3.14`, `py -3.10`, then `py -3`, `python`, `python3`. Each candidate must be 64-bit Python 3.10 - 3.14. Python 3.15 and newer are not supported yet (the packages are not available for them) and 32-bit Python does not work; the message says so - install 64-bit Python 3.13 next to it.
6. **Checks the path length.** Windows limits paths to 260 characters unless "long paths" are turned on, and the longest file in the packages needs about 170 characters inside the install folder. If long paths are off and the `venv` path is longer than 85 characters, the launcher stops with a clear message instead of failing halfway (this only happens with an unusual `PETERPIPER_HOME` or a very long user-profile path).
7. **Creates the private environment** (`python -m venv`; `[1/3]`, about 10 - 30 seconds, nothing is downloaded yet). Nothing is installed into your system Python.
8. **Downloads and installs the packages** with pip, hardened: inherited `PIP_*` settings are cleared and pip configuration files ignored (`PIP_CONFIG_FILE=nul`); the official index is used explicitly over https (`--index-url https://pypi.org/simple`); ready-made packages (wheels) only, nothing is compiled from source (`--only-binary=:all:`); installs only into the private environment (`--require-virtualenv`); no prompts, no cache, and pip itself is never upgraded.
   - With Python 3.11 - 3.14 it installs the **exact list** `requirements.txt`. If that fails, it says so and installs the compatible list instead.
   - With Python 3.10 it goes straight to the **compatible list** `requirements-compatible.txt` and says so. After a fallback, the note at the end says how to try the exact versions again later: delete the `venv` folder and start the `.bat` again.
   - While it installs, a large **PLEASE WAIT FOR INSTALLATIONS** box is shown and the window title says the same: the window can look frozen for minutes (especially at "Installing collected packages") - it is still working; do not close it.
   - **What it is doing** (1.2): pip runs through `app\install_progress.py`, a small script that uses only Python's standard library (so it runs before any package is there). It passes pip's own output through as it comes and, **whenever pip prints nothing for 5 seconds**, adds one line saying what pip is doing, how long the install has taken and roughly how long is left, for example `still working - looking up numpy - 3 of 45 packages (12 s so far)`, `still working - downloading scipy (38.6 MB) - 7 of 45 packages (1 min 5 s so far, about 2 min left)` or `still working - installing numpy, scipy, ... (45 packages; 1 min 40 s so far, about 1 min left)`. The time left is a rough estimate from the megabytes and package files fetched so far (the downloads total about 250 MB). Because pip's output is passed through a pipe, pip draws its own download bars only when each download has finished, not while it runs. pip's exit code is passed on unchanged, so a failed download is reported as before. Without `install_progress.py` the launcher runs pip directly, as in 1.1.
9. **Checks** that every package imports, one by one with a count (`checking numpy ... OK  (1 of 14)` ... `all packages OK`; `[3/3]`, about 10 - 30 seconds); a package that fails is named with its error. If the download worked but this check fails (for example antivirus removed a file), it says so in its own message - different from a failed download - and tells you to delete the `venv` folder and start again.
10. **Records what was installed** in `venv\installed_versions.txt` (date, which list was used, the Python version and platform, then the full `pip freeze` list) and stores the stamp `venv\installed_requirements.txt`. When the compatible list was used, it shows a note asking you to report `installed_versions.txt` for published work.
11. **Makes the PeterPiper shortcuts** (the first time, and again if the folder was moved): *PeterPiper* with the logo icon next to the `.bat`, on the Desktop and in the Start menu (right-click it there to pin it to Start or the taskbar). A `.bat` file cannot have an icon of its own, so the shortcuts carry it; they start the same `.bat`. `PETERPIPER_NO_SHORTCUTS=1` turns this off.
12. **Starts the program** with `pythonw`: `app\PeterPiper.py`, with the logo as its window and taskbar icon. The launcher window shows the logo, says when the window will open (1.2: "Starting PeterPiper - the window opens in about 10-20 seconds." right after an install, when Python first prepares the packages; "Starting PeterPiper - the window opens in a few seconds." otherwise) and *keep this window open*, and closes by itself when you quit PeterPiper. Anything printed before the window appears goes to `%USERPROFILE%\.PeterPiperV1.2\error_<number>.txt`; that file is deleted after a normal exit and opened in Notepad if the program crashes.

### 3.3 Where things are stored

| What | Where | Notes |
|---|---|---|
| The program | The folder you extracted (e.g. `D:\PeterPiperV1.2`) | The program only reads it (Python adds its own `__pycache__` folders of compiled code there). Only *Check for updates*, when you choose *Update now*, changes program files here (section 3.6). |
| Update backups (1.1) | `<program folder>\_update_backup\<old version>_<time>\` | Every program file an in-place update replaced, copied here first (section 3.6). |
| Private Python and packages | `%USERPROFILE%\.PeterPiperV1.2\venv` - or, when the launcher reuses an identical earlier install (1.2, section 3.2), that version's `venv` (e.g. `%USERPROFILE%\.PeterPiperV1.1\venv`) | About 0.5 GB. Delete it to force a fresh install. |
| Installed versions | `installed_versions.txt` in that `venv` (e.g. `%USERPROFILE%\.PeterPiperV1.2\venv\installed_versions.txt`) | The exact package versions on this computer - for methods sections and bug reports. |
| Users | `%USERPROFILE%\PeterPiper data\users.json` and `%USERPROFILE%\PeterPiper data\users\<name>\` | **One folder for every PeterPiper version** (a new version finds everyone's profiles; PeterPiper 1.1 and 1.2 use the users and runs of 1.0 as they are). 1.1: `users.json` also holds the roles, merged users and aliases, this computer's link to a lab folder (`"lab"`) and this computer's own data folders (`"data_folders"`), section 6.16. It starts empty: nothing is taken over from PD4nav, whose `PD4nav data` folder is left as it was (bring a PD4nav profile in on purpose with *Import a profile...*). The list of users, the last one, renames / removed users and *don't ask again* (section 6.0). Everything below marked *per user* is in the user's own folder. |
| Settings | `%USERPROFILE%\PeterPiper data\users\<name>\settings.json` (per user) | Your last-used settings (tracking rules, export list, text size, graph look, ...). |
| Compare colours | `%USERPROFILE%\PeterPiper data\users\<name>\compare_colours.json` (per user) | Colours you chose in the *Compare / average runs* window for unknown cell lines, groups or runs (by name). |
| Compare window choices | `%USERPROFILE%\PeterPiper data\users\<name>\compare_window.json` (per user) | The cell line you chose for each `.nd2` in the *Compare / average runs* window (keyed by its content fingerprint, else the run file's path); each run's group (by run file and by `.nd2` fingerprint) and name in the graph; which runs were ticked, the mode, compartment, quantity, graph and kinetics choices; the list's column order, widths and sort. |
| List of earlier runs | `%USERPROFILE%\PeterPiper data\users\<name>\run_history.json` (per user) | For each analysed `.nd2`: its name, size, fingerprint, paths, and the paths of its ROI / session files. No image data. |
| Where results and back-ups go (1.1) | `...\users\<name>\storage.json` (per user, this computer only) | The results location chosen in *Storage & cloud* (`results_root`; absent = next to each movie) and the back-up folder (`backup_root`), section 6.17. |
| Movie queue (1.1) | `...\users\<name>\queue.json` (per user, this computer only) | The queued `.nd2` paths and each one's status (`todo` / `saved` / `exported` / `skipped`), section 6.14. |
| Smart auto-select (1.1) | `...\users\<name>\smartselect.json` (per user) | Your named bins (name, channel names, date made) and, per hand-drawn queued movie you SAVEd: the `.nd2` path, the saved run file, the channel names, the number of ROIs saved and of ROIs added by hand, its bin. No image data, section 6.15. |
| Charlotte's Web (1.1) | `...\users\<name>\charlotte.json` (per user) | The game's own collection only (random seeds, drawing choices, theme, movie name, date, the number of cells drawn by hand), section 6.19. |
| Hidden extras (1.1) | `...\users\<name>\achievements.json` (per user) | Which optional hidden extras this user has found, and when. Deleting it hides them again. |
| Keep in step (1.1) | `...\users\<name>\sync.json` (per user, never synced) | The folder your profile is kept in step with, the time and result of the last sync, and a checksum per file from the last sync, section 6.16. |
| Password (1.1, optional) | `...\users\<name>\password.json` (per user) | Only a salted hash (PBKDF2-SHA256, 200,000 iterations, 16-byte random salt) - never the password itself; absent or empty = no password, section 6.16. |
| Start-up error log | `%USERPROFILE%\.PeterPiperV1.2\error_<number>.txt` | Only while the program runs; deleted after a normal exit. |
| Older versions not to offer (1.2) | `%USERPROFILE%\PeterPiper data\absorb.json` (this computer) | The folders of older PeterPiper versions for which *Don't ask again for these* was chosen (section 3.8). Delete it to be asked again. |
| Carried over from older versions (1.2) | `%USERPROFILE%\PeterPiper data\logs\PeterPiperV<x.y>\` and `%USERPROFILE%\PeterPiper data\carried over\PeterPiperV<x.y>\` | What an absorbed older version kept for itself: its error logs and `installed_versions.txt` (`logs`), and settings files of which the current user already has a different copy (`carried over`), section 3.8. |
| Results | `OUTPUT_<file name>\<user>` next to the `.nd2` (default, V2.9; you can choose another folder in the start screen); 1.1: or `<your results folder>\OUTPUT_<file name>\<user>` when *Storage & cloud* says *In a folder* | One new `Export_<date>_<time>` folder per export; 1.2: in another folder if one is chosen under *Save in* in the export list (section 6.7). |
| Results when the movie's folder cannot be written | `%USERPROFILE%\PeterPiper results\OUTPUT_<file name>\<user>` (1.0.3) | Suggested when the `.nd2` is on a read-only drive (e.g. a Windows-formatted drive on a Mac), full, or a folder without permission; you can choose another folder instead. |
| Autosaved sessions | `<results folder>\PeterPiper_sessions\` | One file per window session (section 7). Sessions PD4nav saved in `PD4nav_sessions` are still found and opened. |
| Shortcuts | `PeterPiper.lnk` next to the `.bat`, on the Desktop and in the Start menu; `%USERPROFILE%\.PeterPiperV1.2\shortcuts_for.txt` remembers which `.bat` they start | Made by the launcher (section 3.2); 1.2: absorbing an older version points its Desktop and Start-menu shortcuts at this version (section 3.8). |
| Comparisons | `<results folder>\Comparisons\` (default) | *Compare / average runs* outputs (section 6.10). |
| Back-ups (1.1) | `<back-up folder>\PeterPiper backup\<movie>\` | *File > Back up this analysis...*: the `.nd2` (optional) and `OUTPUT_<movie>\<user>` with everything in it; nothing is ever overwritten (section 6.17). |
| Profile kept in step (1.1, optional) | `<your folder>\PeterPiper profile - <name>\` | A copy of your profile, laid out like an exported profile, in a folder you chose (e.g. in your own cloud drive), section 6.16. |
| Lab folder (1.1, optional) | `<lab folder>\PeterPiper lab users.json` and `<lab folder>\PeterPiper profiles\PeterPiper profile - <name>\` | The lab user list (names, aliases, roles, optional password hashes, the lab's data folders, the *anyone can add themselves* switch) and each person's profile, section 6.16. |

Prism style templates, saved settings and the saved-files log are per user too; the computer check's record (`computer_check.json`) is in `%USERPROFILE%\PeterPiper data`. The private Python (`venv`) stays in the version's own `%USERPROFILE%\.PeterPiperV1.2` (or in the earlier version's folder whose install it reuses). On a Mac, `PeterPiper data` is in your home folder (`~/PeterPiper data`) and paths use `/`. With `PETERPIPER_HOME` set, everything listed under `%USERPROFILE%\PeterPiper data` goes into that folder instead.

### 3.4 Exact package versions

`app\requirements.txt` pins all 45 packages - the 13 that PeterPiper uses directly and every package those need - with `==` to the versions of the tested environment (Python 3.11.9 on Windows 11). These exact versions have ready-made packages for 64-bit Windows with Python 3.11, 3.12, 3.13 and 3.14 (checked with pip's resolver for each version). The packages PeterPiper uses directly:

| Package | Version | What PeterPiper uses it for |
|---|---|---|
| numpy | 2.4.6 | All arrays and arithmetic (means, percentiles, ratios). |
| scipy | 1.17.1 | Image filtering and morphology (`scipy.ndimage`: Gaussian smoothing, labelling, dilation / erosion, hole filling, distance transforms, white top-hat); the t distribution for 95% confidence intervals. |
| scikit-image | 0.26.0 | Sub-pixel phase cross-correlation (cell movement), watershed (splitting touching cells), Otsu thresholds, contours, convex hulls, perimeters, disk footprints. |
| nd2 | 0.12.0 | Reading Nikon `.nd2` files and their metadata. |
| dask | 2026.8.0 | Lazy, frame-by-frame access to the `.nd2` data (used through `nd2`). |
| tifffile | 2026.3.3 | Writing the raw 16-bit TIFFs. |
| imagecodecs | 2026.3.6 | Image compression codecs used by the image-file libraries. |
| openpyxl | 3.1.5 | Writing the Excel workbooks (formulas, dropdown, charts). |
| PySide6-Essentials, shiboken6 | 6.12.0 | Qt 6 for Python: the windows, buttons and dialogs. |
| pyqtgraph | 0.14.0 | The image display and the interactive trace panel. |
| matplotlib | 3.11.2 | PNG / SVG graphs and the ROI pictures. |
| pillow | 13.0.0 | The 8-bit "viewing copies" (PNG). |

**V2.5 uses exactly the same package versions as V2.3 and V2.4.** `requirements.txt` and `requirements-compatible.txt` are byte-identical to V2.3's (even their header lines, which still say "PeterPiperV2.3"): the launcher compares the files byte for byte, so this is what lets V2.5 start at once with an existing V2.3 install instead of downloading 250 MB again. **PeterPiper 1.2 uses exactly the same package versions as 1.0 and 1.1**, and its `requirements.txt` and `requirements-compatible.txt` are byte-identical to 1.1's (their header lines still name `PeterPiperV1.1.bat`), so 1.2 reuses an existing 1.1 install (section 3.2, step 4).

If a computer cannot install the exact versions (for example Python 3.10), the launcher installs `requirements-compatible.txt` (version ranges, e.g. `numpy>=1.24,<3`) and says so on screen. Either way, `installed_versions.txt` lists what was really installed. For published work, prefer a computer where the exact versions install.

### 3.5 Options for IT and testing

| Environment variable | Effect |
|---|---|
| `PETERPIPER_HOME=<folder>` | Puts the private environment, settings, run index, compare colours and error logs in `<folder>` instead of `%USERPROFILE%\.PeterPiperV1.2` and `%USERPROFILE%\PeterPiper data`, and turns off reuse of older installs. Use a short path (e.g. `C:\PeterPiper`). |
| `PETERPIPER_INSTALL_ONLY=1` | Installs or checks the install, then exits (code 0) without opening the program; no "press a key" pauses. |
| `PETERPIPER_NO_SHORTCUTS=1` | The launcher makes no *PeterPiper* shortcuts (section 3.2, step 11). |
| `PETERPIPER_NO_ABSORB=1` | 1.2: the start screen never offers to take in older PeterPiper versions (section 3.8). |
| `PETERPIPER_NO_ELEVATE=1` | 1.2: *Turn on Windows long paths* never asks Windows for administrator rights (used by the developer tests; section 6.7). |

Exit codes of the launcher: 0 = OK; 1 = not extracted, no Python, unsuitable Python, install path too long, environment could not be created, download failed, or the program crashed.

### 3.6 Updating, reinstalling and uninstalling

- **Updating to a later version**: extract it into its own folder and start its own `.bat`. Each program version has its own install folder (`.PeterPiperV1.0`, `.PeterPiperV1.1`, `.PeterPiperV1.2`, ...); since 1.2 a new version uses an earlier version's private Python when the package lists are byte-identical (section 3.2, step 4), and otherwise installs its own. **Your profiles, settings and run lists are in `%USERPROFILE%\PeterPiper data` and every later PeterPiper version finds them** (PeterPiper 1.1 and 1.2 find 1.0's users and runs). Once the new version runs, its start screen offers to take the older versions in (section 3.8). Results stay compatible: PeterPiper 1.0, 1.1 and 1.2 open ROI and session files of every PD4nav version (V1.x without tracking, V1.9 - V2.1, V2.2 - V2.4 with tracking, V2.5 - V3.0; tracking made before V2.5 loads with its own background values, see section 7). Files PeterPiper writes say so (`app` = PeterPiper in the file), so *Earlier analyses* and *Compare* show e.g. "PeterPiper 1.1" or "PD4nav 3.0" for each run.
- **Check for updates** (1.1; start screen footer and *Help > Check for updates...*): the only place PeterPiper uses the network, and only when you press it (`peterpiper/updater.py`, `gui/updatedlg.py`). It asks GitHub's public release list of the project (one HTTPS request to `api.github.com/repos/peterdepaola4/PeterPiper/releases/latest`, with a generic User-Agent) for the newest version, shows its release notes, and offers *Update now* (Windows) or *Download* (Mac), *Open the release page* or *Later*. Nothing of yours (names, files, paths, results) is sent. What an update changes:
  - **Windows, the same program folder and the same package list** (e.g. 1.2.0 → 1.2.1): the release zip is downloaded to a temporary folder; only the program files that differ from it are replaced, each first copied to `<program folder>\_update_backup\<old version>_<time>\`. Nothing outside the zip's own file list is touched, and protected paths (`_out`, logs, shortcuts, `.git`, `__pycache__`, `_update_backup` ...) are never written.
  - **Windows, a new program folder or new packages** (e.g. 1.3): the release is unpacked into its own new folder next to the current one (never over an existing folder); start it with its own `.bat`. The current version stays as it is.
  - **Mac**: the `.dmg` for this Mac (Apple chip or Intel) is saved in *Downloads* (never over an existing file) and opened; drag the new app onto Applications.
  - **A developer copy** (a git checkout) is never changed - update it with git.
  - **Your data is never touched**: profiles, settings, run lists, saved files, logs and results live in `PeterPiper data` and next to your movies, outside the program folder. If GitHub cannot be reached (no internet, a firewall), a plain message says so and nothing is changed; if an update does not finish, the message says that nothing of yours was changed.
- **Coming from PD4nav**: PeterPiper starts empty - its users, settings and run list are its own, and PD4nav's (`%USERPROFILE%\PD4nav data`, `.PD4navV...` folders) are left untouched. Your analyses next to the movies are still there: *Earlier analyses of this file* and Compare > *Find my runs in a folder...* find them. To take a whole PD4nav profile over, export it in PD4nav (*Export my profile...*) and import it in PeterPiper (*Import a profile...*).
- **Fresh install** (e.g. after a broken download): delete the `venv` the launcher uses - `%USERPROFILE%\.PeterPiperV1.2\venv`, or the earlier version's `venv` it reuses (section 3.2, step 4; with that one gone and no other identical install left, 1.2 installs its own) - and double-click the `.bat` again.
- **Older versions** (1.2): the start screen offers to take them in (section 3.8): their shortcuts then start 1.2, and their program files and private Python go to the Recycle Bin.
- **Uninstalling**: delete the program folder, `%USERPROFILE%\.PeterPiperV1.2` (also `.PeterPiperV1.1` / `.PeterPiperV1.0` if those versions were installed - the private Python may be in one of them, section 3.2) and the *PeterPiper* shortcuts (Desktop, Start menu). **`%USERPROFILE%\PeterPiper data` holds every user's profile, settings and run list** - keep it if anyone may use PeterPiper again; delete it only to remove PeterPiper and everyone's settings completely. PeterPiper makes no registry entries or system-wide installs (only the three shortcuts; the one exception is Windows' own long-path setting, and only if you press *Turn on Windows long paths* and approve it, section 6.7). Your results (`OUTPUT_...` folders, including `PeterPiper_sessions`) are not touched; delete them by hand if you wish. Python itself is removed through Windows Settings > Apps.

### 3.7 macOS

PeterPiper for Mac is one app, **PeterPiper.app**, that carries its own Python and every package (the exact versions in `app/requirements.txt`), so nothing has to be installed and no internet is needed after the download. It is the same program as on Windows - the same code, the same numbers - built on GitHub's Mac machines for each release (`.github/workflows/mac-app.yml`, `build/peterpiper_app.spec`), where the developer tests run on macOS and the finished app checks itself before it is published (below).

1. **Which download**: `PeterPiper-1.2.1-macOS-AppleChip.dmg` for Macs with an Apple M chip (M1 - M4 ...), `PeterPiper-1.2.1-macOS-Intel.dmg` for Intel Macs. *Apple menu > About This Mac* shows *Chip: Apple M...* or *Processor: ... Intel ...*. Needs **macOS 14 (Sonoma) or newer** (the tested package versions exist for macOS 14 and newer only).
2. **Install**: open the `.dmg`, drag **PeterPiper** onto **Applications**, eject the `.dmg`.
3. **First start**: The first time, macOS says it cannot check PeterPiper for malicious software (PeterPiper is not registered with Apple): click **Done**, open **System Settings > Privacy & Security**, scroll down to *"PeterPiper" was blocked...* and click **Open Anyway**, then **Open** (and your Mac password). From then on it opens with a double-click like any app. After that you can keep it in the Dock (right-click its icon > *Options > Keep in Dock*).
4. **Where things are**: your profiles, settings and run list in `PeterPiper data` in your home folder (Finder > Go > Home); results next to each movie in `OUTPUT_<movie>/<your name>`, as on Windows. **External drives formatted for Windows (NTFS)**: macOS can read them but not write to them, so the results cannot go next to a movie on such a drive - PeterPiper says so and saves them in `PeterPiper results/OUTPUT_<movie>/<your name>` in your home folder instead (or a folder you choose); the movie itself stays on the drive. To keep results next to the movies on a Mac, the drive must be formatted as exFAT or APFS (reformatting erases it - copy everything off first) or have an NTFS driver for macOS installed. If the app ever closes unexpectedly, the report is in `~/Library/Logs/PeterPiper` (Finder > Go > Go to Folder...).
5. **Check an installation**: in Terminal, `/Applications/PeterPiper.app/Contents/MacOS/PeterPiper --selftest` runs a whole analysis of a small built-in synthetic movie and checks the numbers (add a folder and the path of one of your `.nd2` files to also open that movie, read only); it ends with *SELF-TEST PASSED*.
6. **Updating**: drag the new version onto Applications and replace the old one; your data stays. *Check for updates* (1.1) saves the right `.dmg` in Downloads and opens it (section 3.6). **Uninstalling**: move PeterPiper from Applications to the Bin; delete `PeterPiper data` in your home folder only to remove everyone's settings too.

Differences from Windows: there is no `.bat` and no terminal window (no block-character logo) - the app opens straight to *Who is using PeterPiper?*; the Windows long-path setting does not exist on a Mac; *Saved files...* and the Prism style templates open files with their Mac program (GraphPad Prism for Mac opens `.prism` files). Keyboard shortcuts use Cmd where Windows uses Ctrl.

### 3.8 Taking in older versions (1.2)

Profiles, settings and run lists are kept in `PeterPiper data`, which every PeterPiper version shares (section 3.3), so a new version has them from its first start. What each older version keeps **for itself** remains on the computer: its program folder (e.g. `D:\PeterPiperV1.1` with `PeterPiperV1.1.bat` and `app\`), its `%USERPROFILE%\.PeterPiperV<x.y>` folder (the private Python, about 0.5 GB, `shortcuts_for.txt` and start-up error logs) and the *PeterPiper* shortcuts that start it. PeterPiper 1.2 offers to tidy these up ("absorb" them) (`peterpiper/absorb.py`, `gui/absorbdlg.py`).

**Finding older versions.** Once per program start, shortly after the start screen appears, PeterPiper looks - quickly, without searching whole drives - for PeterPiper versions from 1.0 up to (not including) the running one: the `%USERPROFILE%\.PeterPiperV<x.y>` folders, the `.bat` named in each one's `shortcuts_for.txt`, the targets of the `PeterPiper.lnk` shortcuts on the Desktop, in the Start menu and in the running program folder (read from the shortcut files themselves), and `PeterPiperV<x.y>` folders next to the running program folder. A program folder is recognised by its `PeterPiperV<x.y>.bat` next to `app\peterpiper`. PD4nav's folders are never part of this. If a **newer** PeterPiper version is found, nothing is offered (the newest version takes the others in).

**The window** *Older PeterPiper versions are on this computer* (it does not block the start screen) lists each version found with a tick box: its program folder and its private Python, each with its size (counted in the background), and the size of your own files in its folder, which stay. Three buttons:

- **Absorb** - takes the ticked versions in (below) and then says, per version, what was copied and where, which shortcuts now start this version, what went to the Recycle Bin (from which folder) and what was kept, and why;
- **Not now** - nothing is changed; the window comes back at the next start;
- **Don't ask again for these** - these folders are not offered again on this computer (`PeterPiper data\absorb.json`); a folder of such a version that was not seen then is offered again.

**What Absorb does**, for each ticked version, in this order:

1. **Copies what the old version kept for itself into `PeterPiper data`**, never over anything already there: its non-empty error logs and its `venv\installed_versions.txt` into `PeterPiper data\logs\PeterPiperV<x.y>\`; settings files found in its `.PeterPiperV<x.y>` folder into the current user's folder, or - if the user already has a different copy - into `PeterPiper data\carried over\PeterPiperV<x.y>\`; an old run list is merged into the user's (the user's own entries unchanged).
2. **Points the shortcuts at this version**: a Desktop or Start-menu `PeterPiper.lnk` that starts that version's `.bat` (or a PeterPiper `.bat` that no longer exists) is rewritten to start `PeterPiperV1.2.bat`, with the logo icon.
3. **Moves that version's program files and its private Python to the Recycle Bin** (Mac: the Trash), from where they can be restored. Only what is recognised as PeterPiper's moves: in the program folder, its `.bat`, `app\`, `docs\`, `build\`, `__pycache__\`, `_update_backup\`, the README, licence, changelog, citation and contributing files and its shortcut; in `.PeterPiperV<x.y>`, the `venv`, `shortcuts_for.txt` and the error logs. Everything else in those folders - results, notes, movies, any file PeterPiper did not put there - stays where it is and is listed as kept. A folder left empty is then removed. Nothing is deleted for good.

**Never touched**: the running program folder; the private Python the running PeterPiper uses (when the launcher reused an older version's install, section 3.2, that version's `venv` is listed as *kept: PeterPiper 1.2 uses it*); a developer copy (a program folder with `.git`) and the private Python it uses; anything outside the found versions' own folders; `PeterPiper data`.

**Safety checks.** Before anything is moved, every item is checked: if a file in it is in use, or that version is open at the moment (its launcher holds its error log open), nothing of that version is moved and the message says so ("... seems to be open - close it, then try again"). A drive without a Recycle Bin (e.g. a network drive) is refused, so nothing is ever deleted outright. If a move fails part way, that version's removal stops there; what was moved can be restored from the Recycle Bin, the rest is kept, and the reason is given. `PETERPIPER_NO_ABSORB=1` turns the offer off (section 3.5).

On a Mac, a new PeterPiper.app replaces the old one when it is dragged onto Applications, so the app has no older program folders to take in.

## 4. Privacy: everything runs on your computer

- **No data leaves the computer.** PeterPiper never uploads images, results, settings or usage data, and has no accounts, sign-in, licence server or telemetry. The program uses the network in **exactly one place**: the optional **Check for updates** (1.1; start screen footer and *Help > Check for updates...*), and only when you press it - one HTTPS request to GitHub's public release list of the project (`api.github.com/repos/peterdepaola4/PeterPiper/releases/latest`) with a generic User-Agent and, only if you then choose to update, the download of that release's file (section 3.6). Nothing of yours (names, files, paths, results) is sent. Apart from that, the only network use is the one-time package download by the launcher from https://pypi.org (and again only if the package list changes or you delete the install).
- **Cloud and network folders are only folders** (1.1): results, back-ups, a profile kept in step and a lab folder may be put into a folder that OneDrive, Google Drive, Box, Dropbox, iCloud Drive and similar services synchronise, or onto a network drive. PeterPiper only reads and writes those local folders; the service's own app does any uploading. PeterPiper never signs in to any service (section 6.17).
- **Passwords** (1.1, optional, off by default) are never stored: only a salted hash (section 6.16).
- **What it reads**: the `.nd2` and ROI files you choose; to offer earlier analyses it also reads the headers (not the masks) of ROI and session files (`*_ROIs*.npz`, `*_session_*.npz`) in the results folder and next to the `.nd2`; to fingerprint a movie it reads the first and last 4 MiB of the `.nd2` file.
- **What it writes**:
  - results into the results folder you choose (default `OUTPUT_<file name>\<user>` next to the `.nd2`; `PeterPiper results` in your home folder if that cannot be written): one new `Export_<date>_<time>` folder per export, `Save ROIs now` files, and the autosaved session files in `PeterPiper_sessions`;
  - into your own folder in `%USERPROFILE%\PeterPiper data\users\<name>`: `settings.json`, `run_history.json` (file names, paths, sizes and fingerprints - no image data), `compare_colours.json` (names and colours you chose), `compare_window.json` (cell lines you chose per `.nd2` fingerprint or run path, and the list's column layout); 1.1: `storage.json`, `queue.json`, `smartselect.json`, `charlotte.json`, `achievements.json`, `sync.json` and, only if you set a password, `password.json` (a salted hash) - section 3.3 says what each holds; into `%USERPROFILE%\PeterPiper data\users.json` the user list (with roles, aliases and this computer's lab link); into `%USERPROFILE%\.PeterPiperV1.2`, while it runs, a start-up error log;
  - 1.2: exports into the folder chosen under *Save in* in the export list, when you choose one (section 6.7);
  - comparisons into `<results folder>\Comparisons` (or the folder you choose);
  - raw TIFFs only when you ask for them;
  - 1.1, only when you set them up: back-ups into `<back-up folder>\PeterPiper backup\`; your profile into `<your folder>\PeterPiper profile - <name>\`; the lab list and profiles into the lab folder; after *Update now*, changed program files into the program folder (with copies of the old ones in `_update_backup`), or a new version into its own new folder; on a Mac, the downloaded `.dmg` into Downloads.
  - 1.2, only when you press *Absorb* (section 3.8): the older version's logs and settings into `PeterPiper data\logs` and `PeterPiper data\carried over` (or the user's folder), the rewritten Desktop / Start-menu shortcuts, and that version's program files and private Python moved to the Recycle Bin; only after *Don't ask again for these*: `PeterPiper data\absorb.json`; only when you press *Turn on Windows long paths* and approve Windows' administrator prompt: Windows' long-path setting (section 6.7).
  - **PeterPiper writes only into the folders listed here.**
- **Your files are never replaced.** Every result file is created new and exclusively; if the name is taken, `_2`, `_3`, ... is added. The only files PeterPiper replaces are its own: the current session file and the run index (each written to a temporary file first and swapped in with one `os.replace`, so they are never half-written), and its `settings.json`, `compare_colours.json`, `compare_window.json`, the 1.1 per-user files listed above, the lab list and the profile copies it keeps in step (also written via a temporary file and `os.replace`); and, only after *Update now*, program files in the program folder (each copied to `_update_backup` first). Absorbing an older version (1.2) replaces no file: it copies only to names not yet taken, rewrites only the *PeterPiper* shortcuts, and moves that version's own files to the Recycle Bin instead of deleting them.
- **ROI files cannot carry code**: they are NumPy archives read with `allow_pickle=False`.
- Details: `app\SECURITY.md`.

## 5. Quick start

1. Double-click `PeterPiperV1.2.bat` (Mac: PeterPiper in Applications) and pick your name in *Who is using PeterPiper?*.
2. **Start screen**: press **Analyse movies** and choose one `.nd2` - or several at once (Ctrl / Shift-click), which become your **movie queue**; check *Pixel size* and *Frame interval*; press **Open in the analysis window**. (To compare or average runs you saved before, press **Compare / average saved runs** instead - no image needed. **Recent analyses** on the right opens a run straight into the analysis window.)
3. If the movie was analysed before, a list of earlier analyses appears: **Load this run** (ROIs and tracking come back) or **Start a fresh analysis**.
4. **Step 1, Tracking rules**: check the rule, e.g. `Track [Nucleus] using [Cy5] [ONLY]`. Add a rule per kind of ROI (`+ Add rule`).
5. **Step 2, Add ROIs**: pick the Compartment, press **AUTO-DETECT** (the slider under it keeps only the brightest of the cells found) and/or turn on **Add** and click each cell. Fix shapes with Resize (scroll), Split, Merge (1.2: two ROIs that are one cell), Add to cell, Draw by hand; Remove what you do not want. **Pick the background region yourself** (V3.0: it is no longer placed automatically - it often sat on real cells): right-click an empty area > *Put the background region here*, or Compartment *Background* with Add (a 60 µm square) or Draw by hand (a freehand outline). TRACK & MEASURE without one switches straight to placing it.
6. **Step 3**: check *Size may change by* (default ±25%; 0% = exactly the drawn pixel count); if two touching cells get mixed up, use **Tracker boundary** to draw a line between them; press **TRACK & MEASURE**.
7. **Step 4**: press **▶ Play** and watch the outlines follow the cells; tick / untick cells in the list beside the traces.
8. **SAVE** (at the foot of the side panel; optionally type a short note first, e.g. *without the dim cells*): this version of your work is kept as a saved run and shows in Compare as *Saved: <note>*.
9. **Step 5**: set the **Baseline (time 0)**, press **EXPORT...**, put what you want on your export list (1.2: *Save in* shows where it goes; *Change...* for another folder), press **Export**. Open the new `Export_<date>_<time>` folder (the "Open folder" button, or *Open results folder* at the top). The Methods text in it is the start of your methods section.
10. In a queue: **Next movie ▸** at the top opens the next movie still to do (it asks to SAVE first if you changed something); *Skip* passes over one.
11. Several dishes of one condition: **Compare / average runs...**, put the dishes of one condition into one group, show *Groups - mean of dish means (n = dishes)*, **Save...**.

The blue box at the top of the side panel always says what to do next.

## 6. The workflow, step by step

### 6.0 Who is using PeterPiper? (V2.9)

PeterPiper first asks **who is using it** (`peterpiper/users.py`, `gui/userdlg.py`): pick your name (the last user is pre-selected; double-click or *Continue*) or type a new name and press *Add user*. Profiles keep people's work apart on a shared computer; a password is optional and off by default (1.1, section 6.16).

**The window in 1.1.** The main choice comes first (pick your name or add a user). Below it, one *Profile & lab* box shows and changes the selected person's **Keep in step** folder (*Off* or a folder, *Change...*), the computer's **Lab folder** (linked or not; *Lab settings...* for admins and developers), **Merge profiles...**, **Import a profile...** and **More** (*Rename...*, *Remove...*, *Export this profile...*, *Password...*). On the very first start, with nobody on the list yet, the window also offers to link this computer to the lab's shared PeterPiper folder. These are described in section 6.16.

- **Your own folder**: everything PeterPiper remembers - settings, the list of your runs, Compare groups / colours / labels, Prism style templates, saved settings and the saved-files log - is in `%USERPROFILE%\PeterPiper data\users\<your name>\` (the same folder for every PeterPiper version).
- **Your own results**: next to a movie, results go into `OUTPUT_<movie>\<your name>\` (exports, ROI files, autosaved sessions, comparisons).
- **Only your runs**: every ROI / session file records who made it. *Earlier analyses of this file*, the *Analysed before* note, and *Compare / average runs* list only your own; runs you made on another computer (a shared drive) are added with Compare > *Find my runs in a folder...*. Another person's run is opened only on purpose (Compare > *Add run file...*) and is then named with its owner, e.g. "movie1 (Ana's)".
- **A fresh start**: PeterPiper 1.0 starts with no users and takes nothing over from PD4nav (section 3.6 says how to bring a PD4nav profile in on purpose). Results folders from before profiles (`OUTPUT_<movie>` without a user folder) are listed for the first user made only.
- **Rename...** gives a user another name (their folder and runs stay theirs - the old name still identifies runs made before); **Remove...** only takes a name off the list (nothing is deleted; adding the same name again brings the user back). **Enter** continues with the selected name.
- **Your profile goes with you** (portable): everything in your user folder is self-contained and says whose it is (`profile.json`). On another computer either copy the folder into `%USERPROFILE%\PeterPiper data\users\` there (PeterPiper adds it to the list at the next start), or use **Export my profile...** (start window; one `.zip`) and **Import a profile...** there (start window, or *Who is using PeterPiper?*): a new user, or - if a user of that name exists - merged into theirs (runs, groups, colours, labels, templates and saved files added; their settings and anything already there are never overwritten; a differing template is kept as *(imported)*). Your **analyses** stay next to your movies (`OUTPUT_<movie>\<you>`): copy them with the movie folders. Runs whose files are in another place on the new computer: *Compare / average runs* says how many are missing and **My data is in...** finds them - each matched exactly (same movie fingerprint, file name and save time) - and remembers the new place (`moved_data.json`), so later runs from the same old folder are found too. Runs missing on one computer are kept in your list (they may be on another). Compare works from the saved results alone; only steps that need the image (drawing, tracking) need the movie. Nothing is ever sent over the internet.
- **Don't ask again on this Windows account**: for computers where everyone has their own Windows login - PeterPiper then starts straight away as the last user, until *Switch user...*.
- The start screen shows *User: <name>* with **Switch user**; every window title shows the user.

**Computer check** (V2.9, `peterpiper/syscheck.py`, `gui/syscheckdlg.py`). At the first start on a computer (after *Who is using PeterPiper?*), and again only if a result changes, PeterPiper shows what it found - it only looks, it changes nothing; it is always under *Help > Computer check...*:

- **Long file paths**: Windows' *Enable Win32 long paths* setting (`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`). PeterPiper itself reads and writes long paths, but with the setting off (the Windows default) Explorer, Excel and other programs may not open results whose full path is longer than 260 characters. To turn it on, press **Turn on Windows long paths** (1.2; Windows shows its own administrator approval, PeterPiper then reads the setting again and says plainly whether it is on now), or *Copy command* and run it in PowerShell opened with *Run as administrator*. Without administrator rights, ask IT for the Group Policy *Enable Win32 long paths* (Computer Configuration > Administrative Templates > System > Filesystem), which sets `LongPathsEnabled` = 1. Even with the setting on, Explorer and Excel may still not open very long paths - Excel never opens a workbook whose full path is over 218 characters - so short folder and file names stay the safe choice (section 6.7). This button is the only thing in the computer check that changes anything.
- **Python**: the version running PeterPiper - 64-bit Python 3.11 - 3.14 are tested.

GraphPad Prism is not needed to run PeterPiper: it only opens the `.prism` files PeterPiper writes.

### 6.1 The start screen

1.1 redesigned the start window as a **start screen** (`gui/setup.py`). It opens maximized and fits a 1366 x 768 screen without scroll bars. The PeterPiper logo is at the top left (black on light themes, white on dark ones; also in *Who is using PeterPiper?*); at the top right, the **Smart auto-select** status line (✨ when unlocked, 🔒 while locked, with *?* for how it works; section 6.15), *User: <name>* and **Switch user**.

**Three big choices:**

| Choice | What it does |
|---|---|
| **Analyse movies** | Choose one `.nd2` - or several at once (Ctrl / Shift-click). Several become your **movie queue**, analysed one after another (section 6.14); the first still to do is shown in the movie card. |
| **Continue your queue (N left)** | Opens the next movie of your queue that is still to do (shown only while there is one). |
| **Compare / average saved runs** | Opens the window of section 6.10 straight away, without opening an `.nd2`. |

**The movie card** (left) keeps every check of the earlier start window:

| Part | What to do |
|---|---|
| File | The chosen movie's name and folder. Nothing is typed; files and folders are chosen with a browser. If the movie needs a look (below), a warning line says why: *Please check before opening: ...*. |
| Check the file | A summary (timepoints, channels, size, bit depth, file size, total duration, objective). **Pixel size (µm/px)** is read from the file's calibration and **Frame interval (s)** from the frame time stamps (the median spacing; if the file has no usable time stamps, the declared time-loop period; 0 = unknown, time is then given in timepoints). **Uneven gaps (V3.0)**: every frame's time stamp is read; a gap between two timepoints more than 20% off the median is shown in amber under the summary (e.g. *timepoint 1 → 2: 3 h 17 min*, or the longer gap when a treatment was added), and the total is first to last frame as recorded. Graphs and results still space the timepoints evenly at the frame interval, so times next to such a gap are not the real ones; the Methods text and the Settings sheet say so and list the gaps. **Check both**: every size and distance in the analysis is in micrometres and depends on the pixel size, and every time axis depends on the interval. **Stage position** appears for multi-position files: one position is analysed at a time. |
| Channel names | The names read from the file, editable. The names become the Excel sheet names, so they must be different from each other and plain (no slashes, colons, asterisks, question marks, quotation marks, angle brackets or vertical bars). |
| Results folder | Defaults to `OUTPUT_<file name>\<user>` next to the image (or inside the folder chosen in *Storage & cloud*, section 6.17); *Change...* to choose another; **Open results folder** opens it. If it cannot be written (a read-only drive, e.g. a Windows-formatted drive on a Mac; a full drive; no permission), PeterPiper says why and offers `PeterPiper results` in your home folder or another folder (1.0.3). |
| Analysed before | Whether earlier analyses of this movie were found, e.g. "2 earlier runs (newest 29 Oct 2026 17:26, tracking saved). You can load one when the image opens." |

**Open in the analysis window** opens the movie. A large file shows a progress window for a few seconds.

**Older versions** (1.2): once per program start, shortly after the start screen appears, a separate window offers to take in older PeterPiper versions found on the computer (section 3.8); the start screen stays usable meanwhile.

**Tabs on the right:** **Recent analyses** - your newest analyses, one per movie (movie, date saved, cells); double-click or *Open in analysis window* opens the movie with that run loaded (its ROIs and tracking as saved); *Results folder* opens the folder it was saved in. **Queue** (*Queue (N left)*) - the queued movies with their status (*to do*, *saved*, *exported ✓*, *skipped*); *Open*, *Remove* (the file is not touched), *Clear queue*.

**Skipping the start screen.** A movie opened from the queue (*Continue your queue*, *Next movie*) or from a run list (*Recent analyses*, Compare's *Open in analysis*) goes straight into the analysis window **only when its metadata is complete**: a pixel size is present and is not the stand-in 1.0 µm/px, the frame interval is above 0, the gaps between timepoints are even, the file holds a single stage position, and the channel names can be used. Otherwise the start screen opens with that movie and says what to check.

**The footer:** **Saved files** (section 9.13), **Storage & cloud** (section 6.17), **Check for updates** (section 3.6), **More** (*Batch analyse automatically (no clicking)...*, *Prism style templates...*, *Export my profile...*, *Import a profile...*), the text size (`A-` / `A+` / *Reset*, remembered) and the **Theme** (section 6.18).

### 6.2 The main window

- **Left: the image.** Below it: the timepoint slider with ◀ / ▶| buttons, **▶ Play** (space bar) and the play speed (2, 4, 8, 15 or 25 timepoints per second); **Show** (one channel, an overlay of two channels, or - for a WITH rule - the *Tracking image* the ROIs are drawn and followed on); **Fit to window**; **Outlines** and **Cell numbers** on / off. Scroll on the image to zoom, drag to pan. The bar under the image sets the white point (drag it, scroll on it, double-click for automatic); the setting is kept as you step through time, so brightness changes you see are real. On the image, tracker boundary lines are drawn in orange (the selected cell's with a white halo). No background pixels are left out (section 8.4), so no red dots are drawn; only a session tracked with the earlier V2.5 exclusion method still shows the pixels it left out as small red dots (display only, section 7).
- **Right: the side panel**, top to bottom: the **step bar** (V2.9: *1 Rules · 2 ROIs · 3 Track · 4 Check · 5 Export*; the step you are on is lit, finished steps are green - click one to go to it; *1 Rules* stays the current step until you have looked at the rules or added the first ROI), the blue **what-to-do-next** box, **one step page at a time** (1.1: the step bar switches pages; each page ends with a *Next: ...* button; rarely used things - *Load saved ROIs...*, *Earlier analyses of this file...*, *Train auto-detect from my runs...*, *Smart auto-select: your bins...* - are in step 2's **More** menu and the File menu), and at the foot, always visible, a **note** box, **SAVE** and **EXPORT...** (section 6.14), with when you last saved and the autosave **Status**. (Up to 1.0 all five steps were stacked and folded; the pages replace that.)
- **The top row** (1.1): **◂ Another file** (back to the start screen), **Open results folder**, **Compare / average runs...**, **Undo**, and - for a movie in your queue - *Movie 2 of 5*, **Skip** and **Next movie ▸** (*Finish the queue* on the last one).
- **The window opens maximized** (1.1) and, at the default text size, needs no scroll bar on a 1366 x 768 screen.
- **Loading bars** (V2.9): anything that takes more than a moment - opening an `.nd2` (with its first frame), looking for earlier analyses, reading your saved runs for the Compare window, loading the runs you tick, saving a comparison - shows a small window with what it is doing and a progress bar, so the program never looks frozen (the work runs in the background; clicks wait until it is done). Detecting, tracking and exporting keep their progress bar under the image. **1.2**: every such window and the progress strip under the image show (`gui/widgets.py`: `BusyPanel`, `ProgressStrip`, `run_with_progress`, `busy`):
  - a bar with the **percent** done when the amount of work is known, or a moving bar when it is not;
  - the **time**: "about 1 min 20 s left" (estimated from the time so far and the fraction done, smoothed so it does not jump, and counting down between reports), "estimating time left..." until there is enough progress to estimate, "almost done" at the end, or "12 s so far" when the amount of work is not known; when the strip's work is finished it shows how long it took ("took 45 s");
  - **what is happening** (e.g. *Reading your runs*, *Tracking*) and a **detail line** naming what is being read or written: the file or folder, or a count such as *timepoint 12 of 61* or *run 3 of 12 - <file>*. A long path is shortened in the middle (the drive and the file name stay visible) and shown whole when the mouse rests on it; the window never grows wider than the screen;
  - folder searches (*Find my runs in a folder...*, the batch window's folder, the search for earlier analyses) give a real fraction; saving and exporting name each file as it is written. Reading a saved run, filling the start screen's *Recent analyses*, adding several runs with Compare's *Add run file...* and adding a batch folder now have bars too. A window's title is never empty: a drive root such as `D:\` is named in full.
- **Notes that fade** (V2.9): *ROIs saved*, *Exported* and *Graph saved* appear as a banner at the top of the window with **Open folder**, and fade away after a few seconds (they stay while the mouse is on them) - no OK box to click. The same message stays in Status.
- **The Traces panel** (right edge, "Traces - include / exclude cells here") appears after tracking.
- **Menus** (1.1): *File* (Choose another file..., Earlier analyses of this file..., Load saved ROIs..., Save now (SAVE) Ctrl S, Open results folder, Back up this analysis..., Export raw TIFFs..., Compare / average runs..., Prism style templates..., Save / Load analysis settings..., Batch analyse .nd2 files..., Saved files..., Save my work automatically, Offer earlier analyses when a file opens, Close); *View* (Theme: Midnight (dark) / Daylight (light) and any palettes you have found, Larger text Ctrl +, Smaller text Ctrl -, Normal text size Ctrl 0, Undo Ctrl Z, Play / pause Space); *Help* (How to use this window, About PeterPiper, Computer check..., Check for updates..., and *Achievements...* - shown only once a hidden extra has been found).

### 6.3 Step 1: Tracking rules

One rule per kind of ROI (V3.0):

```
Auto-detect [Nucleus ▾]                  ×
    using [GFP ▾]
    helped by [Cy5 ▾]                    ×
    + helper channel
```

- **Compartment**: Nucleus, Whole cell, Cytoplasm or Mitochondria. Each compartment can have one rule; a compartment listed twice uses only its first rule (a note says so).
- **Main channel** ("using"): the channel this kind of ROI is seen on. It is drawn and followed on it.
- **Helper channels** ("+ helper channel", none or several; × removes one). A helper channel does two things:
  1. **It chooses which cells AUTO-DETECT picks**: a cell is proposed only if its signal in every helper channel is at least *Helper signal needed* × its noise (step 3, default **5**; the same test the older IF rule used: mean inside the ROI minus the 25th percentile of a 3 µm ring around it, divided by the channel's background pixel noise). Cells you click yourself are always kept; a note says when one has little helper signal. Example: main GFP (the sensor read-out), helper Cy5 (marks the transfected cells) - AUTO-DETECT then proposes only cells with Cy5 signal.
  2. **It helps follow the cell**: the ROI is drawn and followed on a helper image = the main channel + **0.5 ×** each helper channel (`HELP_WEIGHT`; the main channel counts twice as much as each helper), each scaled between its own background and bright level measured once on the drawn timepoint, and expressed in the main channel's counts:

     ```
     z_main = (main - bg_main) / (top_main - bg_main)
     z_h    = (helper - bg_h) / (top_h - bg_h)
     image  = bg_main + (top_main - bg_main) x (z_main + 0.5 x sum of z_h) / (1 + 0.5 x number of helpers)
     ```

     **Guard against bleeding**: at every timepoint the outline is also drawn on the main channel alone, and the helper-image outline may reach at most **1 µm** beyond it (`HELP_GUARD_UM`; pixels further out are removed; if nothing would be left, the main channel's own outline is used). It never takes a pixel from another cell's ROI of the same compartment (as for every rule). *Show > Tracking image* shows the helper image.
- **What is measured never changes**: every channel is measured in every ROI, whatever the rule.

**Older rules (runs made before V3.0).** The ONLY / WITH / AND / IF rules are no longer offered, but a run made with one loads and is applied **exactly as saved**, so its numbers are reproduced: its second channel is shown as a helper line with a note in V3.0 words (e.g. *From a run made before V3.0: GFP trims the outline (combined image) - applied exactly as saved*). Changing anything in that rule turns it into a V3.0 rule (main + helpers), and the run must be tracked again. The table and the details below describe the older rules.


**V2.5 rule lock.** Every rule follows the cell **exactly as ONLY does**, on the raw pixels of channel A: the outline that is followed from timepoint to timepoint (the "ONLY outline") is the same whatever the mode. Channel B can only **remove pixels** from that outline (WITH, AND - the measured pixels are then a subset of the ONLY outline) or **exclude cells** (IF). No ROI is ever bigger than its ONLY outline, so a bright second channel can no longer make an ROI bleed into a neighbour. (Up to V2.4, WITH outlined and followed the ROI on the combined image itself.)

| Older mode | Shown as | What it did |
|---|---|---|
| **ONLY** | `Track nucleus using Cy5 ONLY` | The ROI is found and followed on channel A alone. |
| **WITH** | `Track whole cell using mRuby WITH intensity in GFP` | The ROI is followed on channel A exactly as ONLY; inside that outline only the pixels where A and B added together (each scaled to its own brightness) are bright are kept (measured). Never bigger than the ONLY outline. |
| **AND** | `Track mitochondria using GFP AND intensity in ExRai` | The ROI is followed on channel A exactly as ONLY; inside that outline only the pixels that are also bright in channel B are kept (measured). Never bigger than the ONLY outline. |
| **IF** | `Track nucleus using Cy5 IF intensity in GFP` | The ROI is followed on channel A exactly as ONLY; a cell is kept only IF it has real signal in channel B (else it is excluded, with the reason shown). Use it to keep only cells that express a sensor. |

How the older modes work, precisely (constants in `peterpiper/rules.py`):

- **Normalisation, frozen at the drawn timepoint.** WITH, AND and IF use per-channel constants measured **once**, on the frame the ROIs are drawn on, and then kept fixed for the whole movie, so the combined image does not rescale itself as cells brighten or dim (`GuideNorm`, `make_norm`). From every 4th pixel in y and x of that frame (`NORM_STRIDE = 4`): background level `bg` = 20th percentile (`NORM_BG_PCT = 20`); bright level `top` = 99.5th percentile (`NORM_TOP_PCT = 99.5`), raised if necessary to at least `bg + max(noise, 1 count)`; noise = 1.4826 x the median absolute deviation (MAD) of the pixels at or below the median (a Gaussian-equivalent SD of the background; 1 count if the MAD is 0). These values are recorded in every export (`norm`).
- **All four modes** follow (move and redraw) on the raw pixels of channel A, unchanged (section 8.5).
- **WITH** uses a combined image in channel A's count units:

  ```
  za    = (A - bgA) / (topA - bgA)
  zb    = (B - bgB) / (topB - bgB)
  guide = bgA + (topA - bgA) x (za + zb) / 2
  ```

  i.e. both channels are scaled so their own background is 0 and their bright level is 1, averaged, and mapped back to channel A's counts. Choose *Show > Tracking image* to see it. At every timepoint (`rules.with_mask`), the combined image is smoothed with the compartment's tracking σ (`SIGMA_UM`, at least 0.8 px); the ROI's measured pixels are those of the ONLY outline where **guide > bg + level x (inside - bg)**, with bg = 20th percentile of the guide in a 4 µm ring around the outline (channel A's frozen background if the ring has fewer than 20 pixels, `WITH_MIN_RING_PX`), inside = the guide's median inside the outline, and **level = the outline's own edge level on the combined image at the drawn timepoint** (computed as in section 8.5 step 0, then frozen). Holes are filled, but never beyond the outline. A timepoint where no pixel is kept measures NaN (quality 0.3). The followed region stays the whole ONLY outline. Note: under WITH, clicking, resizing and AUTO-DETECT in step 2 still draw on the combined image (the "Drawn and followed on" line says `A + B (combined)`); from the drawn timepoint on, the tracker re-outlines that ROI on channel A (within ±10% of the drawn size on the drawn timepoint, section 8.5) and keeps only the pixels described here.
- **AND**: at every timepoint, an ROI pixel is measured only where channel B, smoothed with a Gaussian of σ = 0.5 µm (`AND_SIGMA_UM`; at least 0.5 px), is above the local background of B plus k x B's noise. Local background = the 20th percentile (`AND_BG_PCT`) of smoothed B in a 4 µm ring (`RING_UM`) around the ROI's followed region (if the ring has fewer than 20 pixels, `AND_MIN_RING_PX`, the frozen background of B is used); noise = the frozen noise of B; **k = `overlap_k` = 3**. The followed region itself stays whole (it is what the next timepoint is followed from). A timepoint where no pixel passes gives no value (NaN) for that ROI and is flagged (quality 0.3). On the drawn timepoint the kept pixels are shown as a second outline inside the ROI.
- **IF**: the cell's signal-to-noise in channel B on the drawn timepoint = (mean of B inside the ROI - 25th percentile of B in a 3 µm ring around it, within a window 6 µm larger than the ROI) / B's frozen noise. A cell with **SNR below `gate_snr` = 5** is excluded with the reason, e.g. `no GFP signal (IF gate: SNR 1.3 < 5)`. You can include it again by ticking it. While drawing, a cell that fails gets a warning straight away; AUTO-DETECT skips such cells and says how many. The IF gate is evaluated once, on the drawn timepoint; the outlines and measurements are the same as with ONLY.
- **Neighbours and size** (section 8.5): under every mode the ONLY outline obeys the hard size limit, never shares a pixel with another cell's ROI of the same compartment and never crosses the cell's tracker boundary lines; WITH and AND can only make the measured part smaller still.
- If channel B is missing or the same as channel A, the rule works as ONLY (a note says so).

Other points:

- **Every channel is measured in every ROI, whatever the rules.** The rule only decides where the ROI is.
- **Cells move with the first rule.** Each cell's movement is measured around its ROI of the first rule's compartment (the "lead"; a note under the rules names it). Put the most reliable compartment first (usually the nucleus).
- **`+ Add rule`** adds a rule for the next compartment without one; **x** removes a rule (at least one stays).
- **Changing a rule after tracking clears the tracking** ("The tracking rules changed - press TRACK & MEASURE again."). Undo brings back the earlier rule only together with its tracking.
- If ROIs of a compartment were drawn on another channel than the rule's (e.g. in an older file), a note says they will be followed on the rule's image.
- Rules are remembered (by channel name) for the next movie with the same channel names, and saved in every ROI and session file.
- Hover over a rule for a one-sentence explanation.

### 6.4 Step 2: Add ROIs

- **Compartment**: what Add / Remove / Draw act on, which outlines are highlighted and which traces are shown. Below it, a muted line says what it is **Drawn and followed on**: e.g. `Cy5`, `GFP helped by Cy5 (followed on GFP + half of Cy5; cells need Cy5 signal)`, or for an older rule `mRuby + GFP (combined)`, `GFP (only pixels also bright in ExRai)`, `mRuby (cells need GFP signal)`. Choosing a compartment switches the image to that image. (Under a WITH rule the ROIs are drawn on the combined image but followed on channel A - section 6.3.) The last entry, **Background**, is for placing the background region (below).
- **All ROIs are drawn on one timepoint** (the first one you click on); drawing tools bring the image back to it.

The tools (each is on / off; click it again or press Esc to turn it off). 1.2: the buttons stand in two rows, *Add | Remove | Draw by hand | Resize* and *Split | Merge | Add to cell*:

| Tool | Colour when on | How to use it |
|---|---|---|
| **Add** | green | Click each object: its ROI is drawn around the click from the image (section 8.2). Straight after a click, **scroll** to make it bigger / smaller (redrawn from the image, 12% of area per notch). |
| **Remove** | red | Click an ROI to delete it. |
| **Draw by hand** | orange | Click around an outline; double-click (or right-click) to finish. Cytoplasm: your nucleus ROIs are cut out; mitochondria: the mitochondria inside the outline are found. |
| **Resize** | purple | Click a cell, then scroll: up = bigger, down = smaller, 12% of area per notch, no limit (redrawn from the image each step; other cells' pixels are never taken). *Resize all cells together* does every ROI of the compartment at once. |
| **Split** | teal | Hold the left button and draw a line across an ROI: it is cut along the line into two cells (the ends of the line are continued, so roughly across is enough). |
| **Merge** (1.2) | blue | For two ROIs next to each other that are really one cell (e.g. a nucleus outlined as two pieces): click one ROI, then the one next to it. They become **one ROI that keeps the first one's cell number**; the gap between them is filled, never with another cell's pixels (section 8.2). Only ROIs that touch or nearly touch (up to 3 µm apart) can be merged ("These two ROIs are not next to each other"); a merge is also refused when another cell lies between them. The two cells' other compartments are joined the same way (a compartment only the second cell has comes along). Merging clears the tracking (press TRACK & MEASURE again); Undo brings both ROIs back. Esc after the first click picks again; Esc again turns Merge off. |
| **Add to cell** | pink | Click a cell's ROI, then click each missed part just outside it: that part is outlined from the image and joined to the ROI. |

- **AUTO-DETECT** proposes the well-defined (high-confidence) ROIs of the chosen compartment in a second or two: clearly above background, normal size and shape, separate, not at the image edge (criteria in section 8.3). With helper channels (and under an older IF rule), cells without signal in the helper channel are skipped. Beside it, **Smart auto-select** (1.1) picks cells the way you pick them, learned from your hand-picked movies (section 6.15). Under it, **AUTO-DETECT - <name>** buttons are your trained auto-detects for this movie's channels, and **Train auto-detect from my runs...** (step 2's *More* menu) makes one (section 6.13). Remove any you do not want and add the rest by clicking; **Undo** takes all of them back at once.
- **Brightness slider** (V2.5): after AUTO-DETECT a slider appears under it - "Keep the N brightest of the M found (k placed; dimmest kept: x counts above background)". It starts at the right end (all M kept). Sliding left removes the **dimmest** cells first: the cells found are ranked by their brightness = mean of the detection image (the image the compartment is drawn on) inside the ROI minus the mean of the background region on the same image, at the timepoint shown (section 8.3). The slider stays until you make any other change (then the set is accepted and the slider hides); Undo takes back the whole set.
- **Undo (Ctrl+Z)** takes back the last change (up to 60 steps).
- **No tool on**: clicking a cell selects it (its trace lights up). **Right-click** an ROI to move it to another cell, make it a cell of its own, remove it or select its cell; right-click an empty area to add an ROI there or put the background region there.
- **Cell numbers**: an ROI drawn on top of (or within about half a cell of) another compartment's ROI joins that cell; otherwise it starts a new cell (section 8.2). Two cells never share pixels of the same compartment: a new ROI is trimmed where it touches others.
- **The background region** (green box) is **placed by you** (V3.0; it is no longer placed automatically when a movie opens - the automatic square often sat on real cells; only Batch analysis, with nobody to click, still places it itself). The next-step box reminds you, and TRACK & MEASURE without one switches to placing it. **A run whose background was placed automatically** (made before V2.9, or by Batch analysis) says so when it is loaded - *Check the background* with *Place it again* - since the automatic square may sit on cells. It **may contain non-transfected cells** - their autofluorescence is part of the background you want to subtract (section 8.4). Right-click an empty area > *Put the background region here*, or pick Compartment **Background** and:
  - **Add**: click - a 60 µm square centred on the click (also: right-click an empty area > *Put the background region here*);
  - **Draw by hand**: hold the left button, draw around the region (any shape) and release; drawing again replaces it.

  Whatever the region, **every pixel of it is used at every timepoint** - nothing is left out. After tracking, the background of each channel is checked: if it jumps at some timepoints (for example a bright, dead or passing cell in the region) or drifts, or if measured cells lie inside the region, a box **Background is not steady** says so, with **Redraw background** and **Keep it** (section 8.4).
- **Load saved ROIs...** opens a saved ROI file or autosaved session (section 7).
- The counts under the buttons show how many cells and ROIs of each compartment there are, which channel they were drawn on, the background (automatic / placed by you / drawn by you), the drawn timepoint and which cells have tracker boundary lines.

### 6.5 Step 3: Track and measure

**TRACK & MEASURE** follows every cell through all timepoints - from the drawn timepoint forwards to the end, then backwards to the start - **redrawing every ROI at every timepoint** on its rule's channel A, measures every channel in every ROI, and measures the background at every timepoint (algorithm: sections 8.4, 8.5). Only compartments with a rule are tracked. A progress bar shows the time left; **Stop** cancels without changing anything.

**Size may change by ± %** (default 25%, range **0** - 100% in steps of 5) is the **size guard**: while tracking, each ROI's area must stay within this fraction of the size you drew (and within 0.67 - 1.5 x the previous timepoint's area). A redraw outside that - for example a nucleus spilling into its cytoplasm or into a neighbour - is re-fitted to the nearest allowed size around the cell; if even that fails, the outline is moved with the cell instead and that timepoint is noted in QC. On the drawn timepoint itself the redrawn outline must stay within ±10% of what you drew (otherwise your outline is kept).

Since V2.5 the limit is **hard**: a followed region never has more than (1 + tol) x or fewer than (1 - tol) x the number of pixels you drew. A redraw that is still larger after re-fitting is trimmed to its brightest connected pixels around its middle; a smaller one is grown by its brightest neighbouring pixels - never into another cell or across a boundary line (section 8.5, step 4b). **0%** means: redrawn at every timepoint, then given **exactly** the number of pixels you drew. The limit applies to the followed region (for cytoplasm: the whole cell before the nucleus is removed; for mitochondria: the envelope), so the measured cytoplasm or mitochondria pixel count can still change.

**No overlaps.** Two cells' ROIs of the same compartment never share a pixel at any timepoint (section 8.5, step 4c).

**Tracker boundary** (button under the size setting, with **Remove lines**): lines a cell's ROIs may never cross - for example between two touching cells that the tracker mixes up. Press **Tracker boundary** (it turns orange), click the cell (on one of its ROIs), then click the points of a line and double-click (or right-click / Enter) to finish it; draw as many lines as you need for that cell; press the button again (or Esc) when done. Each line:

- belongs to **that cell only** (other cells ignore it) and stays **fixed in the image** (it does not move with the cell);
- keeps the cell's ROIs, at every timepoint, inside the part of the image between its lines that holds the cell's drawn ROI (the line itself, 3 px thick, is never part of the ROI);
- is drawn in orange (the selected cell's with a white halo), saved with your session and ROI file, and listed in the Settings / Methods sheets and the methods text (cell number and the line's image coordinates).

The lines are stored **by cell number**: if you move an ROI to another cell (right-click > move / make it a cell of its own) it is governed by the lines of the cell it now belongs to. To remove a cell's lines: select the cell and press **Remove lines**, or right-click the cell > *Remove cell N's tracker boundary lines*. Adding or removing a line after tracking clears the tracking; Undo takes it back.

Three more tracking settings sit in the same box (new in V2.4; before, they were only in `settings.json`):

| Setting | Default | What it does |
|---|---|---|
| **Max movement between timepoints µm** | 3.0 (0.5 - 50) | How far a cell may move from one timepoint to the next; each ROI is looked for only within this distance (`max_move_um`; search margin = max(3 px, this in pixels), section 8.5). Raise it for fast cells; lower it if outlines jump to a neighbour. |
| **IF rule: needed signal × noise** | 5.0 (0.5 - 100) | Shown only while a rule uses IF. A cell is kept only if its channel-B signal-to-noise on the drawn timepoint reaches this (`gate_snr`, section 6.3). |
| **AND rule: pixel threshold × noise** | 3.0 (0.5 - 100) | Shown only while a rule uses AND. Only ROI pixels where channel B is above its local background by more than this many times its noise are measured (`overlap_k`, section 6.3). |

They are saved in your settings and with the session / ROI file (loading a file puts its values back in the boxes), and recorded in the Settings and Methods sheets and the methods text.

After tracking, a line reports the percentage of ROI-timepoints that were redrawn (the rest were moved), and - under an IF rule - which cells were excluded for lack of signal. If the background is not steady - automatic region or yours - an orange line in the report and a box **Background is not steady** say which channel jumps at which timepoints (and by up to what fraction of its level), which channel drifts and by how much, and whether measured cells cover part of the region, e.g. "The background region is not steady: GFP jumps at timepoint(s) 12-14 (up to 18% of its level). A bright, dead or passing cell in the region usually causes this. Every pixel of the region was used as it is - redraw the background if you want a steadier region." **Redraw background** switches to Compartment *Background* > *Draw by hand*: draw the new region and press TRACK & MEASURE again. **Keep it** keeps the background as it is. The check never changes a value (section 8.4). The tracking is saved automatically at once (section 7).

Any change to ROIs, the background, the rules, the tracker boundary lines or any of the four tracking settings above (including *Size may change by*) after tracking clears the tracking; the blue box then asks you to track again. Closing the window while tracking runs stops the tracking first (it waits until the work has really stopped before the `.nd2` is closed).

### 6.6 Step 4: Check

- **▶ Play** (or the space bar) plays the movie with the tracked outlines on top; drag the slider to scrub. Check that the outlines follow the cells. *Outlines* / *Cell numbers* switch the overlays off to look at the cells.
- **The Traces panel** ("Traces - include / exclude cells here") is **the** place to include or exclude cells:
  - the **cell list**: each cell with a swatch of its colour and line style (1.1, section 6.18); tick / untick *Include* per cell (only for the compartment shown); *Include all* / *Exclude all*; each row also says why a cell is in or out ("included", "excluded by you", "excluded by the IF rule: ...", or "QC note: ..."); click a row to find the cell (its trace turns orange and its outline is highlighted);
  - **Show**: the quantity plotted - `R/R0 - A/B`, `F/F0 - channel`, `Ratio - A/B` or `Intensity - channel` (background-subtracted counts) for every channel and every ordered channel pair. It opens on your key quantity (the `resp_quantity` setting, default `F/F0 - GFP; R/R0 - GFP/Cy5`, R/R0 first), else R/R0 of the rule's channels A/B, else F/F0 of channel A;
  - **plot**: scroll = zoom, drag = move, *Zoom box* = drag a rectangle, *Reset zoom*; hover a line to read its value; click a line to select its cell; **double-click a line to include / exclude that cell**; click elsewhere to jump the image to that time; the orange line marks the timepoint shown in the image.
- **Two views of the graph**:
  - **Check cells** - for deciding which cells to keep: every cell in its own colour (the same as its outline in the image), excluded cells light grey, the mean of the included cells in blue with a shaded SEM band. *Hide excluded* and *Mean only* simplify it.
  - **As exported** - the graph exactly as it will be exported: only the **included** cells, in your graph style. A style row appears: **Look** (presets: *Prism default - mean ± SEM*, *Mean ± SEM + each cell*, *Mean ± SD*, *Mean ± 95% CI*, *Shaded SEM band*, *Shaded SEM band + each cell*, *Each cell only*), **Error** (SEM, SD, 95% CI or none), bars or shaded band, *Each cell* (thin line per cell), mean colour, **More style...** (every setting: symbols and sizes, line widths, colours, title template, axis titles, fixed axis ranges, font size, dashed line at time 0, legend, picture size, with a live preview) and **Save graph...** (section 6.8). The default look (*Prism default - mean ± SEM*) reproduces the bundled Prism template (V2.5, section 9.4): a 0.59 pt mean line in #28D2F0 with 4.32 pt filled circles, capped SEM error bars, 18 pt axis titles, no cell lines, title `<file> - <compartment> (n = <n>)`. Your look is remembered and saved with the session. **If you saved a graph look in an earlier version**, it is carried over with your settings once: every setting still at the old V2.3/V2.4 default (black 1 pt line, 3 pt circles, 12 pt font) switches to the template value, and anything you changed yourself is kept. A look saved inside an older session file comes back as it was when you load that session; Look > *Prism default - mean ± SEM* restores the template look (a preset keeps your titles, axis ranges and font size). Controls marked `*` are "PNG and live view only". **The look goes into the Prism files too** (V2.4): error type, colours, line widths, symbols, each-cell lines, titles, axis ranges and font size are written into every `.prism` (section 9.4). A few looks Prism cannot draw get the closest Prism look; a small **brown note** under the graph then says exactly what the Prism file shows instead (table in section 9.4). The Look list's last entry, **Load look from a Prism file...**, does the reverse (section 6.9).
- **QC notes** (section 8.11) appear in the cell list; they never exclude a cell by themselves - you decide.

### 6.7 Step 5: Export

- **Baseline (time 0)**: the timepoint where F/F0 = 1 and R/R0 = 1 and time = 0; earlier timepoints get negative times. The Excel workbook keeps a dropdown so you can change it there later.
- **Drift slope T _ to T _** (default T2 - T9): the window for the baseline-drift item (section 8.10).
- **EXPORT...** (1.1: at the foot of the side panel; *CHOOSE OUTPUTS & EXPORT...* before) opens the export list:
  - **Name for the files** (top): every file of this export starts with it (default: the `.nd2` name, first 40 characters), e.g. `MyExp1_nucleus.xlsx`. Letters, numbers, `- _ . ( )` and spaces; it is saved with your session.
  - Left: everything that can be made, grouped by compartment; right: **your export list**. *Add* (or double-click) puts an item on the list, *Remove* takes it off. **Only what is on the list is written.** *Standard set* = Excel workbook, Prism graphs, Prism tables, baseline drift, ROI picture on the drawn timepoint, ROI file, Methods text and the graphs of your key quantities (or, if none of them exists in this movie, every F/F0 and R/R0 graph); *Everything*; *Clear list*. *Remember this list for next time* is on by default.
  - **Prism graph style**: *Built-in* (the bundled template, drawn in **your live graph look**) or *Choose style...* - a `.prism` file whose first graph you styled in Prism (made on an XY table with cells as replicates); every "Prism graphs" file then uses that file with the new numbers. **Own-template rule**: if your file was made from a PeterPiper `.prism` (exported, changed in Prism and saved), it keeps being recognised and your live look is applied to it as well; any other Prism graph keeps its own look and gets only the data and the texts (titles, axis titles), as in V2.3. A `.pzfx` with graphs also works: each `.pzfx` then also comes as `..._with_graphs.pzfx`. *How?* explains it.
  - **Save in** (1.2): the folder this export goes into, shown under the file name (shortened in the middle when long; the whole path on hover) - at first this movie's results folder (*this movie's results folder*). **Change...** chooses another folder, for example a shorter one or a project folder; a folder PeterPiper cannot write in (read-only, full, no permission, gone) is refused with the reason, also if it became unwritable before *Export* is pressed. **Usual folder** goes back to the results folder. The choice is kept for this movie's next export while the window is open. Only the export goes there: the autosaved sessions and SAVE stay in the movie's results folder, and the line says so (*not the movie's results folder - your autosaves stay there*).
  - **Export** writes everything into a **new folder** `Export_<YYYY-MM-DD_HH-MM-SS>\` in the *Save in* folder (by default `OUTPUT_<file name>\<user>\Export_<YYYY-MM-DD_HH-MM-SS>\`), one subfolder per compartment, and offers *Open folder*.

**Paths that are too long** (V3.0; 1.2). With Windows' long-path setting off (the Windows default; *Help > Computer check...*), Explorer and many programs have trouble with a file whose full path is longer than 259 characters, and Excel never opens a workbook whose full path is longer than 218 characters, whatever the setting (`exportpaths.EXCEL_MAX`, `WINDOWS_MAX`). Before writing, PeterPiper works out the full path of every file the export will make (`export.export_names`, `exportpaths.py`). If some would be too long, a warning **Long file paths** says how many files and how long the longest path would be, and offers:

- **Shorten names for me** (the default button; the new name and the longest path it gives are shown first): the *Name for the files* is shortened by cutting out its **middle** (marked `...`; the start and the end stay, since the end usually tells files apart, e.g. `_dish3`), never below 8 characters, and only if that is not enough the export folder gets the short name `Export_<yymmdd>-<hhmm>` (e.g. `Export_261116-1430`; `_2` is added if it is taken). The parts that tell the files of one export apart (compartment, quantity, timepoint) are never changed, so the names stay unique. The aim is every path within 218 characters; failing that, every workbook and CSV within 218 and every other path within 259; failing that, every path within 259 (if even that cannot be reached, the warning says so and recommends a folder higher up). **Graph titles keep the full name**;
- **Show Details...**: the folder, the longest path now and with the shorter names, the new name and the export folder's name;
- **Choose another folder...**: a folder higher up (e.g. `C:\Results`), which is checked again in the same way;
- **Turn on Windows long paths**: Windows shows its own administrator approval; PeterPiper then reads the setting again. If it is on and no workbook or CSV is over Excel's limit, the export goes ahead; otherwise the warning comes back, since Explorer and Excel may still not open very long paths. An account without administrator rights cannot turn it on: ask IT for the Group Policy *Enable Win32 long paths* (`LongPathsEnabled` = 1). The same button is in *Help > Computer check...* (section 6.0);
- **Export anyway**: the usual names (PeterPiper itself writes and reads long paths);
- **Cancel**: nothing is written.

With long paths on, on a Mac, or when the setting cannot be read, there is no warning (as before 1.2).

The items (details of each file in section 9):

| Item | Per | What you get |
|---|---|---|
| Excel workbook (every cell's values) | compartment | `<name>_<compartment>.xlsx`: raw, background-subtracted, F/F0, ratio and R/R0 sheets for every channel and channel pair, Include sheet, Graphs sheet, ROI_info, QC_report, Settings (with the baseline dropdown) and Methods. |
| Prism graphs (.prism, Prism 10+) | compartment | One `.prism` project per quantity with the graph already made in your live graph look (default mean ± SEM) of the included cells, title, axis titles; tables: cells as replicates (the graph's data), mean / SEM / n, each cell by name, and the drift slopes if chosen. |
| Prism tables (.pzfx, any Prism version) | compartment | Per quantity: cells as replicates, mean / SEM / n, each cell; drift dot-plot tables if chosen. |
| CSV tables (one per quantity) | compartment | Every quantity: the included cells + Mean, SEM, n per timepoint. |
| Baseline drift slope T_-T_ per cell | compartment | Excel file of each cell's drift slope per quantity with mean / SEM / n of the included cells, and dot-plot tables in the Prism files. |
| Graph: (quantity) | compartment and quantity | 300 dpi PNG in your graph style (as the *As exported* view). |
| ROIs on the timepoint you drew them / on the last timepoint / on every 10th timepoint | compartment | Full-resolution PNG pictures with every ROI outlined and numbered as in Excel. |
| ROI file (.npz) | experiment | Your ROIs, cells, choices and the whole tracking - to reload later. |
| Methods (text file) | experiment | `<name>_methods.txt`: a ready-to-edit methods section with the rules and every setting used, and references. |
| Raw TIFFs | experiment | Every timepoint and channel, 16-bit raw counts, unchanged. |
| Viewing copies | experiment | 8-bit PNG, contrast-stretched - for looking, not for measuring. |

`File > Export raw TIFFs...` writes the raw TIFFs on their own (into `<results folder>\tiffs`).

### 6.8 Saving one graph (Save graph...)

In the Traces panel's **As exported** view, **Save graph...** saves the graph currently shown - the quantity and the included cells on screen - in its own small dialog:

- as a **Prism project (`.prism`, Prism 10+)** made from the bundled template (or your own style file, with the own-template rule of section 6.7): the data (included cells as replicates), the titles, and **the look shown in the panel** - or the closest Prism look, as the brown note says (section 9.4);
- as a **PNG (300 dpi)** and / or **SVG**, in exactly the look chosen in the panel.

The default folder is `Graphs` inside the results folder and the default name `<file>_<compartment>_<quantity>`. Existing files are never replaced (`_2`, `_3`, ... is added).

### 6.9 Load look from a Prism file

The last entry of the **Look** list (in the *As exported* view, and in *More style...*) is **Load look from a Prism file...**. Choose a `.prism` file you styled in GraphPad Prism - best one PeterPiper wrote, changed in Prism and saved. The live graph then takes on that file's look: error type (SEM / SD / 95% CI / none), colours, line widths, symbol and its size, each-cell lines, axis ranges, font size and titles (titles that only name that file's own data, such as PeterPiper's automatic `<file> - <compartment> (n = ...)`, come back as the automatic ones). A message lists what was taken over and what was kept as you had it, because a `.prism` file does not hold it (show the mean, dashed line at time 0, key, saved picture size). Every later export uses the new look, so the preview and the Prism file match. A file without a usable graph gives a plain message and changes nothing. The look is not a list entry of its own afterwards: choosing it again opens the file dialog again.

### 6.10 Compare / average runs

**Compare / average runs...** - *Compare / average saved runs* on the start screen (no image needed), the top row of the analysis window, or *File > Compare / average runs...* - opens the **Compare / average runs** window: several saved runs in one graph, either one line per run or **replicate dishes grouped and averaged**.

**The window in 1.1.** It opens maximized and needs no scroll bars on a 1366 x 768 screen (only a long run list scrolls inside itself). Eight buttons replace the earlier twenty: above the list **Add runs ▾** (*Add run file...*, *Find my runs in a folder...*, *My data is in...*), **Groups ▾** (new group, put the selected runs in a group, rename, delete, take out, group by cell line), **Open in analysis**, **Output files ▾** and **List ▾** (remove from list - also the Delete key -, untick all, open / close all folders, columns shown); under the graph **Save...**, **More ▾** (save / load plot settings, batch save, Prism style templates) and **Reset zoom**; a right-click menu on the list offers the same. The list has taller rows and plainer column titles, and two new columns: **Save** - which kind of save a row is: *Saved: <your note>* (or *Saved*), *Autosave* or *Export* (section 6.14) - and **User** (who made the analysis). Rarely needed columns start hidden (right-click a column title to show them). 1.2: a **Close** button at the bottom right closes the window exactly as its X does (your choices are remembered); *Add run file...* with several files reads them in the background with a loading bar (section 6.2).

- **Open in analysis** (or double-click a run) closes the window and opens the run's movie in the analysis window with that run loaded, to check or change it. The movie is looked for where it was when the run was saved, then where this movie (its fingerprint) was last opened on this computer, then next to the run's `OUTPUT_` folder; a candidate must have the same content fingerprint. If none is found you are asked where the movie is now, and a movie whose contents differ from the run's is opened only after a question. The movie skips the start screen only when its metadata is complete (section 6.1).
- **Output files ▾**: *Open results folder* (the run's results folder), *This run's output files...* (a short list of its exports `Export_...`, autosaves and comparisons, each opened with a click) and *Every saved file...* (section 9.13).
- Lines without a cell-line colour get Okabe-Ito colours (without the pale yellow); pale dots get a darker edge on the white graph.

**The window, in three steps (V2.8).** (1) **Tick the runs to plot** in the run list - ticked runs are shown in **bold** with their colour, the others are dimmed and not plotted. The list is in **folders by group** (in the order the groups were made; *No group* last). Each folder row says how many of its dishes are plotted and shows the group's colour (double-click it to change it, double-click the name to rename the group); its tick plots all its dishes. Inside, a **▸ movie sub-folder** holds the analyses of one `.nd2` that was analysed more than once (newest first) - it is one dish: tick the analysis you want. (2) **Replicate dishes**: *+ New group*, then **drag runs onto the group's folder** (or select runs - Ctrl / Shift-click - and *Put selected runs in ▾*); *Take out of group*, *Rename group*, *Delete group* (its runs move to *No group*), *Group by cell line*. A movie's analyses always move together. Putting runs in a group ticks them and shows *Groups - mean of dish means*; switching to a Groups mode keeps only the newest ticked analysis of each movie (and says so). (3) **Say what to plot** with the plot builder below. Hover any dropdown entry for what it is and what it is good for. **Drag the dividers** between the list, the settings (they scroll) and the graph to make any part bigger - no part can be dragged away to nothing; the window keeps a sensible minimum size, and the divider positions are remembered.

**What to plot - the plot builder** (V2.7; V2.8: every measure). Under *What to show*, the graph is described as a sentence of dropdowns:

> **Plot** [R/R0 ▼] of [GFP ▼] over [Cy5 ▼] in the [Nucleus ▼] **vs** [Time ▼]

- **Plot** (Y): the measure, of a channel (*over* a second channel for the two-channel ratios), in a compartment (nucleus, cytoplasm, whole cell, mitochondria). Every number is the export's own arithmetic (sections 8.6, 8.7; `compare.measure_data`), one value per cell and timepoint:

  | Measure | What it is |
|---|---|
  | R/R0 | ratio A / B (both background-subtracted) ÷ its value at the baseline timepoint |
  | F/F0 | background-subtracted intensity ÷ its value at the baseline timepoint |
  | ΔR/R0, ΔF/F0 | R/R0 − 1, F/F0 − 1 (the change as a fraction) |
  | Ratio | A / B, background-subtracted, **not normalised** |
  | Intensity | ROI mean − background mean (counts) |
  | Raw intensity | ROI mean, background **not** subtracted (counts) |
  | Sum intensity | (ROI mean − background) × ROI area in px: the total signal |
  | Background | the background region's mean: **one value per timepoint for the dish**, not per cell |
  | Compartment ratio | intensity of the channel in this compartment ÷ in another, per cell (e.g. *nucleus over the cytoplasm* = N/C ratio); only cells included in both |
  | Compartment ratio ÷ baseline | the same, ÷ its value at the baseline timepoint |
  | Area | ROI area in µm² (px when the pixel size is not recorded) |

  The lists only offer what **every ticked run** has.
- **vs** (X): **Time** (minutes from each run's baseline - the usual time course), **Timepoint** (frame numbers from the baseline) or **another measure** built the same way, e.g. *Plot F/F0 of GFP in the nucleus vs R/R0 of mCherry over Cy5 in the cytoplasm*. X and Y are then measured **in the same cells**: a cell is used only when it is included in both compartments (a cell keeps its number in every compartment). **Points**: *Trajectory* (default) - one point per timepoint, the mean of X and the mean of Y over the replicates (each run: its cells; *Groups - mean of dish means*: the dish means, n = dishes; pooled: all cells), with error bars on **both** X and Y, joined in time order; *Each cell at one timepoint* (frames after each run's baseline; 0 = the baseline timepoint) or *Each cell, mean over a window of timepoints* (NaN values left out) - one dot per cell (per dish for *mean of dish means*). The kinetics graphs need X = Time.
- **Right Y axis**: *none*, or a second measure drawn dashed on a right Y axis against the same X (V2.8: also when X is a measure) - for two measures with different units. In the `.prism` file it is its own table and graph (Prism's right-axis setting could not be written reliably); in the pictures it is a right axis; in the tables its own sheet / CSV.
- A bold line under the rows says the plot in words (*Plot F/F0 of GFP in the nucleus vs time.*), and the choice is remembered. A **red line** says when a plot does not make sense as asked - X the same as Y, the right axis the same as Y, or *Background* (a dish measure) asked per cell (it is then drawn per timepoint, and never paired cell by cell).
- **The baseline** (V2.9): a time course has a dashed vertical line at time 0 - every run's baseline, where all runs are aligned - in the window and in the saved pictures (Prism files: add one in Prism).
- **The graph** (V2.8): the error is **mean ± SD by default** (the spread of the cells or dishes; SEM, 95% CI or none under *Error* - remembered). Above the graph, **Y error bars** (on by default, as bars or the band of the graph look), **X error bars** (when X is a measure; off by default - with many cells they are wide and hide the curve), **Each cell** (every cell, or every dish for *mean of dish means*, drawn faintly behind its mean - to see the spread and odd cells) and **Reset zoom** (drag to move, scroll to zoom). **Click a legend entry to hide or show that line** (with its error bars and cells). **Hover a point** to read its values (with its error) under the graph. A trajectory (Y vs a measure, one point per timepoint) marks its **start** (○, the baseline) and its **last timepoint** (▲); a dot plot (each cell / dish) shows each line's **mean ± error as a cross**.
- **Save...** (V2.8) asks which file types and kinetics graphs to write, then the name and folder; every save is added to **Saved files...** (section 9.13).
- **Save plot settings... / Load plot settings...**: the whole plot (measures, points, what is shown, error, baseline, title, file types, kinetics graphs) as a named settings file (section 6.12). **Batch save...**: pick several saved plot settings; each is plotted for the ticked runs and saved (every ticked file type) into one folder.

Files for X = a measure: `<name>.prism` (X = the mean X of each point, Y = the replicates, so Prism draws the Y error; the X replicates are in a table of their own - Prism 11's X error-bar format could not be written reliably, so X error bars are in the pictures and tables only), the pictures, `<name>.csv` / `.xlsx` (per point: X and Y mean, SEM, SD, n; or each cell's X and Y).

**Terms.** A **run** is one saved, tracked analysis of one `.nd2` movie. PeterPiper treats each run as one **dish** (one coverslip / well imaged as one movie: many cells, one condition). A **group** is the set of dishes of one condition (e.g. "U2OS NLS-met": three dishes).

- **What counts as a run**: an ROI or session file (`.npz`) **saved with its tracking** (every ROI at every timepoint and the measurements) - any export's ROI file, *Save ROIs now* after tracking, or an autosaved session after tracking. The list is filled from the earlier analyses of the open movie and this computer's run index (section 9.12); *Add run file...* adds any other one; *Find my runs in a folder...* (V3.0) looks through a folder and its subfolders (e.g. the lab's shared drive) for your tracked runs - also ones made on another computer - and adds them to your list (other users' runs are counted, not listed); a file without tracking is refused with a plain message saying how to make one. *Remove from list* only takes it off the list (the file is not touched).
- **Columns**: *Use* (tick boxes drawn light, so they show on the dark list), *Colour* (double-click to change it; remembered), *Name in the graph* (editable, default the `.nd2` name), **Version** (the PeterPiper version that saved the analysis, e.g. *PeterPiperV2.7*, and for a movie analysed more than once which analysis it is: *newest of 2*) and **Saved** (below), **Group (replicate dishes)** (set with the group folders), **Cell line** (a dropdown, below), `.nd2` file (its tooltip names the run file and any identical copies), **Movie folder** (the folder of the `.nd2`, so two different movies with the same file name can be told apart), cells, baseline, frame interval.
- **One row per analysis** (V2.6): an export writes the ROI file and the program also autosaves a session - two files with **identical contents** (the same content key: ROIs, tracking, measurements and settings, section 7). They are listed **once**, as the file you saved (the export's ROI file, or *Save ROIs now*); the autosaved session is named in the `.nd2` file's tooltip. A session saved after you changed something (another ROI, an exclusion, re-tracking) has other contents and is its own row - a real second version.
- **Cell line**: shows the cell line recognised from the name (below), or *Unknown*. If the automatic match is wrong, pick the run's cell line from its dropdown (*Unknown*, then every known cell line, sorted) or **type a new name**. The run is recoloured in that line's shades; for a new name its colour is asked once (then remembered by name, like any colour). The choice wins over the name match and is **remembered for that `.nd2`** - keyed by its content fingerprint (so every analysis of that movie shares it, even renamed or moved), else the run file's path - in `compare_window.json` next to `settings.json`, also after restarting; names you typed appear in every dropdown. **Group by cell line** uses it.
- **Sorting and columns**: click a column title to sort the list by it (numbers as numbers, dates by date, names in natural order - dish 2 before dish 10); click again to reverse. Drag a title to move its column. Every row keeps its run, tick, colour, group and cell line. The column order, widths and sort are remembered (`compare_window.json`).
- **Same .nd2 as**: runs made from the same `.nd2` movie - the same content fingerprint, else the same `.nd2` path (case and slashes ignored), else the same file name and size; two runs whose fingerprints are both known and differ are never the same - are shown together in one **▸ movie folder** (V2.8; the folder and its analyses share a colour). They are one dish: in the *Groups* modes ticking one analysis unticks the movie's others (one dish must not be counted twice); in *Each run* you may tick several to compare the analyses, with a **red note**, and **Save...** asks first.
- **Version** (V2.6): every set of runs made from one `.nd2` gets **its own colour** (in *.nd2 file*, *Same .nd2 as* and *Version*), and *Version* says which analysis it is by the date each run was saved: `newest (3 of 3)`, `older (2 of 3)`, `oldest (1 of 3)`; a movie analysed once says `only analysis`. *Same .nd2 as* names the other analyses with their save time, e.g. `movie1 (saved 1 Nov 2026 21:52)`. Older analyses have their name in italics. *Version* and *Saved* sit right after the name (moved there once in a list whose column order was remembered from before). The list is sorted by *Version*, newest first, by default: the newest analyses are on top and the older analyses of the same `.nd2` sit right under the newest one.
- **Remembered** (V2.6, `compare_window.json`): each run's **group** (by its run file and by its `.nd2` fingerprint - a new analysis of a dish that is already in a group joins that group), its *Name in the graph*, **which runs were ticked**, *Show*, compartment, quantity, *Graph* and the kinetics choices. Reopening the window brings them back; you do not group the dishes again.
- **Grouping**: type the same name in the *Group* column of each dish of a condition, or select rows and **Put in group...**, or **Group by cell line** (every ticked run without a group goes into the group of its cell line - the one chosen in its dropdown, else the recognised one). A ticked run without a group is a group of its own.
- **Show** (three modes):

| Show | One line per | Each line | n |
|---|---|---|---|
| *Each run - mean of its cells* | run | the mean of that run's included cells ± error across its cells (the V2.4 comparison) | included cells of the run with a value at that time |
| *Groups - mean of dish means* | group | **the replicate statistic**: the mean of the dish means ± error across the dishes | **dishes** with a value at that time |
| *Groups - all cells pooled* | group | every included cell of every dish as one sample (for reference only) | cells with a value at that time |

- **Compartment and quantity**: only those that **every ticked run** has are offered; channels are **matched by name**, so runs whose channels are in a different order still compare the same quantity.
- **Baseline**: *Each run's own saved baseline* (default), or untick it and choose one timepoint for all runs.
- **Error**: mean ± SD (default; the same choice as your graph look in the main window and the exports - changing it here changes it there), ± SEM, ± 95% CI or the mean only; an optional **Title** (automatic: `<quantity> - <compartment>`).
- **Time axis and alignment**: time from each run's own baseline, in minutes from each run's own frame interval (in timepoints if any run's interval is unknown). In the group modes **only the frame times that every dish of a group has are averaged; nothing is interpolated** (section 8.8). A brown note under the graph says when dishes were imaged at different intervals or for different lengths and how many timepoints of each were left out; a dish without included cells is left out of its group and named.
- **Graph** (V2.6): *Time course* (the lines above), or one **kinetics** parameter - *t½ max*, *Initial rise slope*, *Maximum rate*, *Time to max*, *Amplitude* or *10-90% rise time* (definitions below) - drawn as a dot plot: each dish (run) a dot, each group its mean as a bar with the chosen error (SEM / SD / 95% CI) **across the dishes**; the axis labels give n dishes. The line under the graph lists the values (mean ± error, n dishes), the time window used and any flags. **Kinetics: the same time window for every dish** (ticked by default): every dish is measured from its baseline to the end of the shortest dish shown, so a movie that simply ran longer does not get a bigger maximum and a later t½ (a curve still changing at its end would otherwise look slower the longer it was imaged). Untick it to measure each dish to its own last frame.
- **The legend** gives n: e.g. `U2OS NLS-met (n = 3 dishes, 412 cells)`, or `... pooled (n = 412 cells, 3 dishes)`.
- **Save...** writes, under one name, into `<results folder>\Comparisons\` (default) - **never overwriting** (`_2`, `_3`, ... is added). Tick the file types (default: Prism, PNG, SVG, CSV and Excel; JPEG, TIFF and PDF on request):
  - **`.prism`** (Prism 10+), in the built-in template look (section 9.4): one data set per line, with a legend. In *Groups - mean of dish means* the replicates of a data set are the **dish means** (one column per dish), so Prism itself draws the mean ± SEM across dishes; in *Each run* and *pooled* the replicates are the cells. Extra tables: per line *mean, SEM, n*; for groups also *each dish mean* and the statistic not plotted (pooled cells, or mean of dish means);
  - **PNG / JPEG / TIFF** (300 dpi; JPEG quality 95, TIFF LZW-compressed) and **SVG / PDF** (text kept as text): the graph as shown, the key right of the plot (the figure is 1.45 x the graph width), the template's symbol per line (circle, square, triangle, triangle down, then diamond and open shapes), a plain (not bold) title;
  - **CSV**: `<name>.csv` = the plotted statistic, one row per line per (common) time: mean, SEM, SD, 95% CI half-width, n (and for groups the numbers of dishes and included cells); for groups also `<name>_per_dish.csv` (each dish's mean, SEM, SD and n over its own cells at every common time, with its `.nd2`, run file, baseline and frame interval) and `<name>_pooled.csv` (or `<name>_dish_means.csv` when the pooled cells are plotted);
  - **Excel (`.xlsx`)**: the same tables as sheets *Graph data*, *Per dish*, *Pooled cells* (or *Mean of dish means*) and *Methods* (a methods text of the comparison: what was averaged, n, alignment, each dish with its `.nd2`, included cells, baseline, interval and run file);
  - **Kinetics graphs** (V2.6; tick them under *Kinetics graphs*, default *t½ max* and *Initial rise slope*, plus the one shown if *Graph* is a kinetics parameter): for each, `<name>_t-half-max`, `_initial-slope`, `_max-rate`, `_time-to-max`, `_amplitude` or `_rise-10-90` in every ticked picture format and as a **`.prism` with the graph made** (the built-in template: one data set per group at X = 1, 2, 3 ... with the dishes' values as its replicates, so Prism draws the mean ± error across dishes; the legend names the groups with n dishes; plus a column table, one column per group and one row per dish, for a scatter dot plot or bar graph made in Prism in one step). The kinetics tables are written whenever a kinetics graph is: `<name>_kinetics_per_dish.csv` (every parameter of every dish, its baseline level and frames, peak, flags) and `<name>_kinetics_groups.csv` (per group and parameter: mean, SD, SEM, 95% CI, n dishes, the value of the group mean curve for reference, each dish's value), also as the Excel sheets *Kinetics per dish* and *Kinetics groups*; the methods text describes the kinetics.

**Kinetics** (V2.6, `peterpiper/kinetics.py`). How fast each dish responds after its baseline - e.g. how fast a rescue rises. Every number comes from **one curve per dish**: the dish mean (the mean of its included cells at every timepoint - the same curve the group average is made of), on the dish's own time axis from its own baseline (time 0 = its baseline timepoint). Nothing is smoothed or fitted to a model.

| Parameter | How it is computed |
|---|---|
| Window | time 0 to the window end: the end of the shortest dish shown (default), or each dish's own last frame |
| Baseline level | the curve's value **at the baseline timepoint** (time 0) - the same reference F/F0 and R/R0 are normalised to; frames before it are not averaged in (they often still drift) |
| Peak, time to max | the time in the window where the curve is furthest from the baseline level (a rise or a fall: the larger change wins; *Response* in the table says which) |
| Amplitude | peak - baseline level (signed) |
| t10, **t½ max**, t90 | the first time after 0 the curve reaches baseline + 10 / 50 / 90 % of the amplitude, **linearly interpolated between the two frames on either side of the crossing** (searched from time 0 up to the peak) |
| 10-90% rise time | t90 - t10 |
| **Initial rise slope** | least-squares straight line through the curve from time 0 up to and including the first frame at or past half-maximum (at least 2 frames; the number used is in *Slope frames*) - the initial rate of the rise, in quantity per minute (per timepoint if the frame interval is not known) |
| Maximum rate | the steepest step between two consecutive frames from time 0 up to the peak |

**Groups**: each parameter's mean, SD (n - 1), SEM = SD / √n and 95% CI = t(0.975, n - 1) × SEM **over the dishes** (n = dishes with a value; each dish counts once). The kinetics of the group's mean curve is listed for reference only - it is not the mean of the dish values. **Flags** are written next to the numbers and under the graph, never hidden: *max (or min) at the end of the window - may still be rising (falling)* (the curve had not levelled off within the window: its maximum, and so t½, describe the response up to that time); *change smaller than 3 SD of the baseline frames - no clear response* (SD of the last 5 frames up to time 0; only with ≥ 3 such frames); no frame at or before / after the baseline. A noisy curve's maximum is its highest frame, so noise raises it slightly; the time resolution is the frame interval (t½ is interpolated between frames).

**Colours by cell line.** Unless you chose it in the *Cell line* dropdown, the window reads the cell line from each run's name (its *Name in the graph*, else its `.nd2` name) or each group's name (else its first dish's `.nd2` name) and colours every line of one cell line in ordered shades of that line's **colour family** (`peterpiper/celllines.py`):

- a reference list of **520 cell lines** (with about 1000 aliases) in **18 colour families**: U2OS and bone / sarcoma reds, HeLa and cervix / uterus oranges, skin / melanoma / head and neck / thyroid golds, prostate / bladder olives, pancreas limes, IHH and immortalised hepatocyte greens, A549 and lung teals, brain / nerve / eye cyans, COS-7 and monkey sky blues, HepG2 and liver blues, Jurkat and blood indigos, HEK293 and kidney purples, MCF10A and ovary magentas, MCF7 and breast-cancer pinks, HCT116 and colon / stomach browns, endothelial / muscle / heart maroons, NIH3T3 / fibroblast / stem-cell greys, CHO / hamster / insect slates;
- matching is case-insensitive, ignores separators (`- _ . /`, spaces, parentheses) and **folds look-alike characters**: O/0, I/1/l, S/5, B/8, Z/2 (so `U20S` = `U2OS` = `u2-os`); the longest (most specific) alias wins (HEK293T before HEK293); short aliases (under 4 characters) and names that are also ordinary words must stand as a separate token (CHO in `cho_dish2`, not in `anchor`), except a few lab names that may run on (IHH in `ihhnlsmet`, HEK in `hekcells`);
- the 1st, 2nd, 3rd ... line of one family gets the family's 1st, 2nd, 3rd ... shade (mid tone, then darker, lighter, ...; adjacent shades differ by at least 0.12 in lightness);
- **unknown cell line**: the window asks once for a colour for that name; the choice, and any colour you change by double-clicking, is **remembered by name** in `compare_colours.json` (next to `settings.json`) and used again next time.

The colours are only a look: they never change a number.

### 6.11 Prism style templates (V2.7)

**File > Prism style templates...** (also under *More* on the start screen and in the Compare window). Every `.prism` PeterPiper writes is made from two files PeterPiper keeps for you in `%USERPROFILE%\PeterPiper data\users\<name>\Prism style templates\` (`peterpiper/prismtemplate.py`):

- **`PeterPiper graph style.prism`** - an example time course. Open it in Prism (*Edit graph style in Prism*), change anything on **graph 1** - fonts, sizes, colours, symbols, line widths, axes, frame, legend - and save it under the same name. From then on every XY graph PeterPiper writes (single runs, *Save graph...*, Compare, averages, and the graph of every other table) is a copy of it with your data and texts.
- **`PeterPiper column graph style.prism`** - an example kinetics table **without** a graph. In Prism select the table *Example groups*, *New graph > Column > scatter dot plot* (or bars) with mean ± SEM, style it and save. Every column table PeterPiper writes (kinetics, drift per cell) then gets a graph made from it (automatic Y range; the groups in table order). Until then column tables are written without a graph.
- *Use this look for PeterPiper's pictures too* reads graph 1's look (error, colours, line widths, symbols, axis ranges, font size; *Load look from a Prism file*, section 6.9) into the graph style, so PNG / SVG / PDF match. *Reset* renames your file `(old 1)` (never deleted) and writes PeterPiper's look again. The files are remembered: they stay in the folder for every later session.
- **To make your look the default of a later version**, send the developer these two files (`dev_tests/make_prism_template.py` builds the bundled template from the first).
- Only the **look** is taken from the files; data, titles, axis titles, legend text and n always come from your runs. A template chosen in the export dialog (*Choose style...*) still wins for that export.

### 6.12 Saved settings and batch analysis (V2.7)

**Saved settings** (`peterpiper/presets.py`) are named `.json` files in `%USERPROFILE%\PeterPiper data\users\<name>\Saved settings\` (or anywhere you save them):

- **File > Save analysis settings...** stores every analysis setting: the tracking rules (by channel **name**, so a file with its channels in another order means the same), detection, size limits, background size, QC, IF-gate and AND settings, the baseline timepoint, the export list and the graph look. **File > Load analysis settings...** uses them from now on (ROIs and tracking already made are not changed; press AUTO-DETECT / TRACK again).
- **Save / Load plot settings...** in the Compare window (section 6.10) store the plot.
- **Batch analyse .nd2 files...** (start screen *More > Batch analyse automatically (no clicking)...* and File menu; `gui/batchdlg.py`): add .nd2 files or a folder (all `.nd2` in it and below), choose saved analysis settings (or the settings in use), *Run*. Each file goes through exactly the steps of the main window, with the same code: the automatic background region, AUTO-DETECT for every compartment that has a tracking rule (in rule order), TRACK & MEASURE, then the settings' export list (else the standard list) into the file's `OUTPUT_<name>` folder, with the ROI file, methods text and provenance as always. No dialog waits for a click; your own `settings.json` is not changed. **Save exports in** (1.2; *Change...*, *Usual folders*): one folder for the batch's exports - each movie's export then goes to `<chosen folder>\<movie name>\Export_<date>_<time>\`, so the movies stay apart, and the batch log goes there too; the runs themselves (autosaves) stay in each movie's results folder. A folder that cannot be written is refused. **Long paths** (1.2): with Windows' long paths off, a batch export whose paths would be too long gets shorter names by itself, exactly as *Shorten names for me* (section 6.7), and the log's messages say so (the old and new name and the longest path). A log `PeterPiper batch <date>.csv` next to the first file (or in the chosen export folder) lists per file: status, cells found and included per compartment, any background note, the export folder and every message. **Nothing is checked by hand, so every file is flagged *automatic - check*** - open it (*File > Earlier analyses of this file*) to check or correct it before you use its numbers.
- **Batch save...** in the Compare window re-plots analysed runs with several saved plot settings at once (section 6.10).

### 6.13 Train auto-detect (V3.0)

AUTO-DETECT on its own proposes every clearly visible nucleus - in a dish with a few transfected cells among many untransfected ones that can be 50 blobs when you want 6. **Train auto-detect from my runs...** (step 2, under AUTO-DETECT) teaches it which cells **you** pick, from runs you have already outlined by hand, and saves that as your own button.

1. **Your runs and channels.** Choose the main channel and the helper channels (e.g. main GFP, helper Cy5), and tick saved runs where you outlined the nuclei you want (by hand, or after fixing AUTO-DETECT). One run per movie is listed (the newest); runs whose `.nd2` is not on this computer, or that lack these channels, are greyed out. Only the frame you drew on is read from each `.nd2` (read-only). Two or more movies give an honest score; more and more varied movies give a better rule. Tick only runs where you picked cells the way you want them picked.
2. **How well it does.** *Learn from the ticked runs* searches for the rule (below) and shows a **scoreboard**: for each movie, your cells, how many it found, missed and added, and its F1 (1 = exactly your picks) - each movie scored with a rule learned from the **other** movies, the honest number for a movie it has not seen. Click a movie to see it: **green** = it picked one of yours, **red** = one of yours it missed, **yellow** = an extra it picked. The learned rule is shown in plain words (read-only; train again to change it).
3. **Quick quiz.** *Start the quiz* shows the 12 blobs it is least sure about (nearest the rule's limits; half just kept, half just left out), each as small pictures of the main and helper channels with its outline: **Keep** (K), **Skip** (S) or **Not sure** (N). Your answers replace the match for those blobs (*Not sure* leaves the blob out of the scoring), the rule is searched again, and you can do *Another 12*. A blob you answered is never asked again.
4. **Save** with a name, e.g. *Autodetect - Nuclear GFP plus Cy5 (my sensor)*. It becomes a button **AUTO-DETECT - <name>** under AUTO-DETECT for every movie with the same channel names (hover for its rule and score). Pressing it is a full preset: the compartment's rule becomes its main channel + helpers, then it picks the cells; the slider, Remove, Add and Undo work as after AUTO-DETECT. Saving under a name you already have asks first. Detectors are files in your profile (`Auto-detect\<name>.json`), so *Export my profile...* takes them along.

**How the rule is learned** (`peterpiper/detectors.py`; every number is in the detector file and in the Methods sheet of every export that used it):

- **Candidates**: on the frame you drew on, every nucleus-sized blob is outlined exactly as AUTO-DETECT does (difference of Gaussians, outlined like a click; permissive limits 10 - 3000 µm², solidity ≥ 0.5) on the helper image, the main channel and each helper channel; a blob found again on a later image (overlap > 50 %) is not added twice.
- **What each blob is judged on**: area (µm²), circularity (4π area / perimeter²) and, for the main channel and every helper, its **signal-to-noise** (as above) and its **relative brightness** = that signal-to-noise ÷ the 95th percentile of all blobs of the movie (1 = as bright as the movie's brightest blobs - so a brighter or dimmer dish is judged the same way).
- **Your picks**: a blob is yours when it is the best match (overlap = intersection / union ≥ 0.3) of one of the nucleus ROIs you saved. Every ROI you saved counts, so one the finder never outlined counts as missed.
- **The rule**: a minimum signal-to-noise (0 or 1 - 300, 30 steps on a log scale) and a minimum relative brightness (0 - 1.2 in steps of 0.05) per channel, a minimum area (0 - 100 µm²), a maximum area (200 - 3000 µm²) and a minimum circularity (0 - 0.75), each from a fixed list, chosen one at a time (up to 6 rounds) so that the **mean F1 over your movies** is highest. A limit that makes no difference stays off; when several values are equally good the middle one is taken (furthest from both edges of what works - safer on a new movie).

**What to expect** (the lab's own data, `test_v30.py` part L): trained on 8 hand-analysed biosensor movies (GFP + Cy5), each movie scored with a rule learned from the other 7, it found 94 of the 142 hand-picked cells with 56 extras (mean F1 0.66); plain AUTO-DETECT on the same movies found 91 with 154 extras (F1 0.50). It does not read your mind: where you picked differently from dish to dish (all bright cells in one, a few in another) no single rule fits, and the quiz is the quickest way to tighten it. Always check the cells it picks.

PeterPiper 1.1's **Smart auto-select** (section 6.15) uses this same method, trained without a quiz on bins of movies you hand-picked in a movie queue.


### 6.14 Movie queue and SAVE (1.1)

**The movie queue** (`peterpiper/batchqueue.py`). Choosing several `.nd2` files at once with **Analyse movies** makes them your queue: they are analysed **by hand, one after another**, each with every check and choice of a single movie (unlike *Batch analyse*, section 6.12, which runs without clicking). The queue is kept per user (`queue.json`, this computer only), so it survives closing PeterPiper; choosing more movies adds them (a movie already in the queue keeps its status). Each movie has a status:

| Status | Set when |
|---|---|
| *to do* | the movie was put into the queue |
| *saved* | you pressed SAVE on it |
| *exported ✓* | an export finished (a later SAVE does not change *exported* back to *saved*) |
| *skipped* | you pressed *Skip* |

In the analysis window the top row shows *Movie 2 of 5* (its tooltip: how many others are still to do), **Skip** and **Next movie ▸**. *Next movie* opens the next movie still *to do* after this one (going round to the start of the list); if you changed the analysis since the last SAVE it first asks **SAVE, then next movie** / *Next movie without saving* / *Cancel* (your work is kept by the autosave either way). On the last movie the button reads *Finish the queue*, and a message says that every movie has been looked at. The start screen's *Queue* tab lists every queued movie with its status; *Continue your queue (N left)* picks up where you stopped. A queued movie opens without the start screen only when its metadata is complete (section 6.1).

**SAVE** (at the foot of the side panel, always visible; also *File > Save now (SAVE)*, Ctrl S). It writes the analysis as it is now - ROIs, cells, include / exclude choices and, once tracked, the whole tracking - as a saved ROI file `<file name>_ROIs.npz` in the results folder (never replacing an existing file: `_2`, `_3` ... is added), of kind `saved` (section 9.11), and adds it to your run list. The optional **note** typed in the box above it (up to 120 characters, e.g. *without the dim cells*; Enter also saves) is stored in the file's summary (`note`). The run then appears in Compare's *Save* column and in *File > Earlier analyses of this file* as **Saved: <note>** (or *Saved*), so different saved versions of one movie can be told apart. A SAVE before tracking keeps the ROIs only and says so. SAVE is in addition to the autosave (section 7), which is unchanged: autosaved sessions are listed as *Autosave*, ROI files written by an export as *Export*. The line under the buttons says when you last saved.

**EXPORT...** (next to SAVE) opens the export list of section 6.7.

### 6.15 Smart auto-select (1.1)

**Smart auto-select** (`peterpiper/smartselect.py`; the button beside AUTO-DETECT in step 2) picks the cells on a movie **the way you pick them**, learned from movies of the same kind in which you picked the cells by hand. Its purpose is to make automated selection on large data sets follow the researcher's own judgement: a few movies annotated carefully by hand teach it which nuclei you include - for example only the transfected cells - and it then applies that rule to new movies, where you review its proposals as after AUTO-DETECT. The method is the trained auto-detect of PD4nav V3.0 (section 6.13), described in full in section 8.13.

- **Bins, one per kind of experiment.** Each user keeps named **bins** (e.g. *GFP/Cy5 nuclei*). Every movie in a bin has the same channel names; a movie may hold any number of ROIs. A bin's **n** is the number of hand-picked movies in it. The button shows the bin that fits the open movie's channels and its n, e.g. **Smart auto-select: GFP/Cy5 nuclei (n=44)**; when several of your bins fit, the button opens a small menu (one entry per bin, with its n, and *Your bins...*).
- **Unlocking.** Smart auto-select is shown to everyone, locked (🔒) until earned: draw the cells **by hand** (at least one ROI added by hand, e.g. with *Add* or *Draw by hand*) on **3 movies from a movie queue** and press **SAVE** on each. Hovering over the locked button, or *?* on the start screen, explains this. Each such movie is recorded in `smartselect.json` (section 3.3; no image data).
- **Sorting movies into bins.** New hand-drawn movies are put into bins in the window **Your Smart auto-select bins**, which opens from the button (and from step 2's *More > Smart auto-select: your bins...*): each movie is listed with its ROIs saved, the ROIs drawn by hand and its channels, and gets a bin from a dropdown - an existing bin with the same channels, *(not in a bin)*, or **New bin...** (you name it). A bin name used for other channels is refused.
- **Using it.** Press the button. PeterPiper learns, in the background, from every movie of the bin that is still on this computer (the saved run file and the `.nd2` must both be found) and that has the channels of the open movie's nucleus rule (main channel and helpers); **at least 2 such movies** are needed (otherwise a message says how many there are). The learned rule then picks this movie's nuclei like a trained auto-detect: the brightness slider, Remove, Add and Undo work as after AUTO-DETECT. It learns again each time it is used, so newly added movies count at once.
- **What it learns.** Nucleus selection (as the trained auto-detect does); other compartments follow from your tracking rules as usual.
- **What is recorded.** The detector's name carries the bin, its n and the number of ROIs it learned from, e.g. *GFP/Cy5 nuclei - Smart auto-select (n=44 hand-picked movies, 612 ROIs)* (an example). Its rule, this name and its held-out score are saved with the run and written into the methods text of every run that used it (section 8.13; how to report it: section 11.3).
- **Plain AUTO-DETECT and your trained auto-detects** (section 6.13) are unchanged and always available.

### 6.16 Profiles, lab folder and roles (1.1)

PeterPiper 1.1 lets one person's profile follow them between computers and lets a lab keep one list of its users (`peterpiper/users.py`, `profilesync.py`, `labshare.py`; `gui/userdlg.py`). Everything below works through ordinary folders; PeterPiper never signs in anywhere (section 4).

**Merge profiles...** (in *Who is using PeterPiper?*). For the same person under two spellings on one computer (e.g. *Ana Lopez* and *A. Lopez*), or for a profile `.zip` or folder from another computer, merged **into** a user you choose. The rules (the kept profile wins every tie):

- `settings.json`: the kept user's settings stay; settings it does not have are added; the merged user's own settings are also kept as a saved setting *Settings of <name>*;
- the run list: every run of both - movies matched by fingerprint, runs united by file path;
- every other JSON file of the profile (Compare colours and choices, the 1.1 files ...): united key by key; where both have a single value for the same key, the kept profile's value stays;
- logs (`*.jsonl`): lines united; other files (Prism style templates, saved settings, trained auto-detects): new ones copied, a different file of the same name kept next to it as *<name> (from <other>)* / *(imported)*;
- per-computer files (`storage.json`, `queue.json`, `sync.json`) are not taken over;
- the merged user is then **hidden, never deleted** (adding the name again brings it back), and its name becomes an **alias** of the kept user, so runs and `OUTPUT_<movie>\<old name>` results made under the old name count as the kept user's.

**Keep in step through a folder** (*Profile & lab > Keep in step*, `profilesync.py`). Choose a folder you can reach from each of your computers - your own OneDrive, Google Drive, Box, Dropbox or iCloud Drive folder, or a network folder. Your profile is kept there as `PeterPiper profile - <name>` (laid out like an exported profile) and is merged both ways **when you start PeterPiper as that user, when you switch user and when PeterPiper closes**. **When this computer is linked to a lab folder** (below), the lab folder already keeps each person's profile in step, in its `PeterPiper profiles` folder: the window says so, and since 1.2.1 the lab folder itself, or a folder inside it, cannot be chosen here (`profilesync.lab_conflict`) - a second copy would sit in the lab's shared folder, where everyone in the lab sees it. A personal folder that 1.2.0 allowed there is no longer used (the note says so); the lab folder's copy carries on. Rules - nothing is deleted and nothing is overwritten blindly:

- a file only one side has is copied to the other; the run list is united (movies by fingerprint, runs by path - a Mac path and a Windows path of the same run are both kept);
- every other JSON file is united key by key; **only where both sides changed the same single value since the last sync does the newer file win**, and a side that did not change since the last sync never wins over one that did (a checksum per file is remembered in `sync.json`);
- logs are united line by line; for other files, the changed one is taken, and if both changed, the newer keeps the name and the older is kept next to it as *<name> (other copy <date>)*;
- per-computer files (results location, movie queue, sync state) are never synced; every write goes to a temporary file first; a folder that is offline or missing is skipped quietly, with a note.

The profile folder's name may differ from your local name (e.g. *Ana Lopez* here, *A. Lopez* on the Mac): the profile is bound by the chosen folder, and the other spelling becomes one of your aliases.

**Lab folder** (*Profile & lab > Lab settings...*, admins and developers; `labshare.py`). An admin **creates** a lab folder on a lab server or a shared cloud folder (choosing which users of this computer to include; whoever creates it is admin in it) or **links** this computer to an existing one. The lab folder holds `PeterPiper lab users.json` (the lab user list) and `PeterPiper profiles\` (each person's profile). On every linked computer:

- the lab user list updates *Who is using PeterPiper?*: new lab members appear; **aliases unite spellings** (a local user whose name or alias is any of a lab person's names is that person, and their runs count as theirs on every computer); nobody is removed because the list changed, and a person is hidden only when the lab list says so (never deleted);
- roles and passwords come from the list (the newer change wins); each person's profile is also kept in step with their folder in the lab folder (when they are chosen and when PeterPiper closes);
- **the lab's data folders** - where the lab's `.nd2` movies live, with a label each - are shared to every linked computer (without a lab, a computer keeps its own list);
- **Anyone can add themselves on a lab computer** (a switch, on when a lab folder is created): a user added on a linked computer is added to the lab list; with the switch off, only an admin can add people.

Conflicts (two computers writing at once, or a cloud app's conflict copies such as *PeterPiper lab users (1).json*) are resolved by reading and uniting every `PeterPiper lab users*.json` in the folder: people are united by any shared name or alias, and for single values the newer change wins. A read-only lab folder is only read (the window says so). The link is per **computer** (in `users.json`), not per user.

**Roles.** **User** (the default), **Admin** and **Developer**. Developer is a title only, with the same abilities as Admin. Admins may open *Lab settings*, change other people's roles, reset passwords and manage the lab list. The first user on a computer is Admin (when nobody visible has the role, the user who took over the older data, else the first user on the list, is treated as Admin), and so is the creator of a lab folder. **The last admin cannot be demoted** - make someone else admin first (this holds on the computer and in the lab list).

**Optional passwords** (*More > Password...*; off by default). Only a salted hash is stored: PBKDF2-SHA256 with **200,000 iterations** and a **16-byte random salt** per password (`password.json` in the user's folder and, when a lab folder is linked, in the lab list), compared in constant time; the password itself is never written anywhere. An admin can reset (clear) another user's password. As the window says, a password keeps profiles tidy and private between colleagues; **it is not strong security** - the files are on a shared disk.

### 6.17 Storage & cloud (1.1)

**Storage & cloud** (start screen footer; `peterpiper/cloud.py`, `gui/storagedlg.py`) puts results and back-ups into folders that cloud services or network drives keep in step - **through each service's own sync app**: OneDrive (including SharePoint and Teams libraries synced through it), Google Drive for desktop, Box Drive, Dropbox, iCloud Drive, Nextcloud / ownCloud, pCloud, MEGA, Sync.com, Egnyte, and network drives. **PeterPiper only reads and writes those local folders; it never signs in, and the service's app does the uploading.** The window lists the folders it finds on this computer (from the services' default folders and, on Windows, read-only registry entries; network drives are listed but not opened, so a server that is off cannot make PeterPiper hang), and *Other folder...* chooses any folder.

- **Results go**: **next to each movie** (default: `OUTPUT_<movie>\<user>` beside the `.nd2`) or **in a folder** - results then go into `<folder>\OUTPUT_<movie>\<user>` (in a cloud place, `<place>\PeterPiper results` is suggested so `OUTPUT_` folders do not fill its top level). A folder that cannot be written is refused with the reason. Kept per user (`storage.json`, this computer only).
- **Back up this analysis...** (*File* menu of the analysis window) copies the movie's results folder (`OUTPUT_<movie>\<user>`: sessions, ROI files, exports) and, optionally, the `.nd2` itself into `<back-up folder>\PeterPiper backup\<movie>\`, with the results under `OUTPUT_<movie>\<user>` inside it, as next to the movie. **Nothing is ever overwritten**: a file already there with the same size and modification time (within 2 s) is skipped; a different file of the same name gets `_2`, `_3` ...; a different movie of the same name gets its own folder `<movie>_2`. Each file is copied to a hidden partial file, its size is checked, and only then is it given its name; free space is checked first; *Stop* leaves what is fully copied and removes what is half-copied (starting again copies nothing twice). A progress bar shows what is copied.
- **Movies stored only online.** When a movie's data is not on this computer (a OneDrive / Google Drive / iCloud placeholder - only the file's attributes are read), PeterPiper warns that it will be downloaded first, with its size.

### 6.18 Colours, themes and accessibility (1.1)

**Cell colours** (`gui/widgets.py`, checked by `gui/colourvision.py`). Every cell's outline, trace and list swatch has the same colour in every theme, from six colours chosen to be colour-blind safe: **#2299CC, #BB2200, #5533FF, #AA8844, #EE3388, #007755** - the hues of Okabe and Ito's colour-blind-safe palette (sky blue, vermillion, blue, orange, reddish purple, bluish green) moved to medium luminance and then tuned to be as far apart as possible. Each has a WCAG 2 contrast of at least **3.23:1** against the white trace plot and at least **3.30:1** against black (the dark image behind the outlines). Every pair of the six is at least **14.4** apart in CIEDE2000 colour difference, with normal vision and with protanopia, deuteranopia and tritanopia simulated (Machado et al. 2009, severity 1.0). Beyond six cells the colours repeat with **dashed, dotted and dash-dot** lines (24 distinct looks before any repeat); the cell numbers on the image tell repeated outline colours apart. The interactive trace plot area is always white, whatever the theme, and the cell list shows a colour swatch (with the line style) next to each cell's name in normal text colour, instead of coloured text. Graphs you export are unchanged (section 8.9).

**Themes** (*View > Theme*, the start screen's *Theme*; `gui/theme.py`). The two basic themes, **Midnight** (dark, the default) and **Daylight** (light), are always offered; 18 further colour palettes become available as one of PeterPiper's optional hidden extras. **Every theme is checked against WCAG 2 contrast minimums** (`theme.validate`): text on the window, panels and inputs at least **7:1**; secondary (muted) text at least **4.5:1**; text on the accent colour at least **4.5:1**; the status colours (warning, error, OK) used as text at least **4.5:1**; text on a selected row at least 4.5:1; the accent used for headings and focus frames at least 3:1; the logo at least 4.5:1; borders at least **1.25:1**. The basic themes' colours were adjusted slightly in 1.1 to meet these limits. Colours never change a number.

### 6.19 Engagement and annotation incentives (1.1)

Careful hand annotation is what makes Smart auto-select match your judgement (section 6.15), so PeterPiper 1.1 rewards it with a small game, **Charlotte's Web** (the pink **🕸 Charlotte's Web** button; `gui/charlotte*.py`):

- every movie whose cells you pick by hand grows its own **unique, procedurally drawn web**, in one of **50 themes** (about a quarter of them are not spiders); each cell ROI added by hand makes it more elaborate (removing one may snap a thread, but a web never unspins);
- **SAVE finishes the web** with one kind word written into it;
- finished webs go into a **collection** (a gallery), and can be **exported as pictures** (PNG); webs of a movie queue are collected together at the end of the batch;
- each web gets a rarity when it starts: of every three webs a user starts, two are **Common** and every third is **Rare** (75%) or **Epic** (25%).

**Charlotte's Web never affects data, measurements or results.** It only listens to what happens in the analysis window, stores only its own small file (`charlotte.json`) in your user folder, draws everything in code (no image files) and uses no network; a failure in it can never disturb an analysis. PeterPiper also contains a few **optional hidden extras** (for example the extra colour palettes of section 6.18); like the game, they never touch data, and *Help > Achievements...* lists the ones a user has found.

## 7. Session memory: your work is kept

**Autosave.** As you work, PeterPiper keeps one session file per window session in `<results folder>\PeterPiper_sessions\<file name>_session_<YYYY-MM-DD_HH-MM-SS>.npz` (the date and time the window was opened). It holds everything a saved ROI file holds: ROIs, cells, include / exclude choices and their reasons, background, drawn timepoint, tracking rules, baseline, drift window, graph look, file-name prefix, and - once tracked - **the tracking** (every ROI at every timepoint and all measurements). It is saved about 2 seconds after your last change (`AUTOSAVE_MS = 2000`), at once after tracking and after an export, and when the window closes. Packing happens in the window and writing in a background thread, so the window never freezes. Each save replaces this one file in a single step (temporary file, then swap), so it is never half-written; it never replaces any other file. The Status box says when it was last saved ("with the tracking" or "ROIs only - not tracked yet"). *File > Save my work automatically* turns this off. Just loading an earlier run and looking at it does not create a new session file.

**No duplicate saves (V2.5).** Every ROI / session file carries a **content key** (`content_key`): a SHA-1 hash of every array in the file (name, data type, shape and bytes - the ROIs, the tracking and all measurements) plus the saved state **without** the fields that only say when or by what it was saved (`saved`, `session_id`, `kind`, `based_on`, `version`, `nd2_path`; of the `.nd2` fingerprint only the quick hash and size are used). Two saves of an unchanged analysis therefore have the same key. An autosave whose key equals that of the last file saved or loaded in this window is **not written** (so exporting, or loading a run and looking at it, does not leave a second identical file). Files from before V2.5 have no key stored; for them a key is computed from the zip's own CRC-32 and size of every array plus the normalised state (nothing is decoded), which matches only other such files.

**Earlier analyses.** When you open a movie, PeterPiper looks for earlier analyses of it - in the results folder (up to 3 folders deep), in `OUTPUT_<file name>` next to the `.nd2`, in older results folders (`ROInav_results`, `PD4nav*_results`), next to the `.nd2` itself, and in this computer's list of earlier runs (`run_history.json`). It recognises a movie by name **and** by fingerprint, so a renamed or moved copy is still found. If any are found (and you have not drawn anything yet), the dialog **"This file has been analysed before"** lists them, newest first, **one entry per identical analysis**: files with the same content key are listed once (the newest), and its details say "N older identical save(s) (same ROIs, tracking and settings) not listed: ..." (the files themselves are never touched):

| Column | Meaning |
|---|---|
| Saved | When the file was saved. |
| Version | The PeterPiper version that made it. |
| Cells | Number of cells. |
| Compartments | Which kinds of ROI. |
| Tracking | "saved ✓" if the file holds the tracking, else "not saved". |
| Kind | autosave (session file), export (ROI file written by an export) or saved (SAVE, 1.1, with its note; *Save ROIs now* before). |
| Folder | Where it is (hover for the full path). |

The details area shows the rules, drawn timepoint, number of timepoints, baseline, path and the **match**: *same file* (the fingerprint matches), *same name* (same name and image size, no fingerprint to compare) or *renamed copy* (found by fingerprint under another name), with a caution if the `.nd2` changed since or the tracking length differs. **Load this run** (preselected: the newest run; when a newer run has no tracking saved, or an older one has, the details say so) or **Start a fresh analysis**. *Don't ask again for any file* turns the question off (*File > Offer earlier analyses when a file opens* turns it back on). *File > Earlier analyses of this file...* lists them at any time (then the second button is *Keep what I have*; what you have is autosaved first).

**What loads.** Loading a run restores the ROIs and cells, include / exclude choices, background (and how it was made: automatic, clicked square or drawn by hand), tracker boundary lines, drawn timepoint, rules, baseline, drift window, graph look and file-name prefix, and **the tracking** if it fits this movie: scrub or Play and the outlines follow the cells exactly as they were tracked; export straight away, no re-tracking. If the saved tracking cannot be used, PeterPiper says exactly why (made before tracking was saved in ROI files; different number of timepoints - a different or shortened movie; different number of cells or channels; a compartment this session does not track; damaged) and asks **"Track now? It takes about N s"** - Yes tracks and the result is saved with this run.

**Older files.**

- **V2.3 / V2.4** files load with their tracking unchanged - including their **background values**, which were measured the pre-V2.5 way (one fixed mask, bright pixels found when the region was placed left out at every timepoint). The Methods sheet then says "fixed mask (before V2.5)", and the Sum_ sheets and the background pixel counts are empty (not recorded). To get the V2.5 background and the sums, press TRACK & MEASURE again (this re-tracks; the numbers can then differ slightly).
- **V2.5 sessions tracked with the earlier V2.5 background method** (very bright and fast-moving objects and the measured ROIs left out at every timepoint, method label `per-timepoint exclusions v2.5`) keep their background values; their Settings sheet and methods text describe that method, and the pixels they left out are still shown as red dots. To get the all-pixels background, press TRACK & MEASURE again.
- **V2.2** ROI files hold the tracking and load with it. They hold no tracking rules: each followed compartment gets an ONLY rule on the channel most of its ROIs were drawn on.
- **V2.1 / V2.0 / V1.9** ROI files hold ROIs and choices but no tracking: they load, the outlines stay where they were drawn, and you are asked whether to track now.
- **V1.x** ROI files (ROIs only) load as well.
- If one compartment's ROIs were drawn on different channels in an old file, a note explains that PeterPiper (since V2.3) follows each kind of ROI on one image (its rule's), and which one.

**Other ways to save and load**: **SAVE** (1.1; *File > Save now (SAVE)*, Ctrl S; *File > Save ROIs now* before) writes `<results folder>\<file name>_ROIs.npz` (never replacing an existing one); every export can include the ROI file; *Load saved ROIs...* opens any `*_ROIs*.npz` or `*_session_*.npz` file.

## 8. How the numbers are made (methods detail)

This section describes the algorithms as implemented in PeterPiperV1.2 (`app/peterpiper/`); 1.1 and 1.2 did not change any of them (section 12). 1.2 adds one ROI editing tool, *Merge* (section 8.2), which changes only the ROIs you merge; tracking and measurement are unchanged. Constant names are given in `code` so every number can be checked in the source. µm values are converted to pixels with the pixel size checked in the start window; "px" values are in image pixels.

### 8.1 Reading the images

- `.nd2` files are read with the `nd2` package (Talley Lambert), lazily through `dask`, one timepoint at a time (`nd2io.ND2Source`). Each timepoint is a stack of all channels (C x Y x X) of 16-bit (or the file's bit depth) raw counts.
- Z stacks are reduced to the **maximum-intensity projection** over Z. Multi-position files: one stage position (chosen on the start screen) per analysis.
- Channel names come from the file's metadata (made unique and safe as sheet names) and can be renamed at start-up.
- Pixel size = the file's x voxel size; frame interval = the median difference of the time stamps of about 12 frames spread over the movie, or the declared time-loop period; both are shown for checking.
- **Saturation level** = 2^(bit depth) - 1 counts (65535 for 16-bit).
- No pixel value is ever changed. Smoothing and filters are used only to find outlines; every measurement uses the raw pixels.

### 8.2 Drawing ROIs at a click

All drawing works on the compartment's rule image (raw channel A for ONLY / AND / IF; the combined image for WITH), in a window around the click, so it is instant on any image size (`manual.py`). "Robust noise" below = 1.4826 x the median absolute deviation (`compartments._robust_noise`).

**Nucleus** (`draw_nucleus`, `_nucleus_at`):

1. A window of ±25 µm around the click (when nuclei already exist: 2.5 x the typical nucleus radius from the median nucleus area, limited to 15 - 60 µm) is smoothed with a Gaussian (σ = 0.8 µm, at least 1 px).
2. The seed is the brightest smoothed pixel within ±2 µm of the click (the click may be a little off-centre).
3. Inside brightness = the median of a 2.5 µm-radius disc around the seed; local background = the 15th percentile of the window; noise = robust noise of the raw pixels in the darker 40% of the window. The nucleus must be brighter than background by more than 3 x the noise.
4. The nucleus = the connected region around the seed above **background + 0.35 x (inside - background)**, holes filled. If the median of that whole region is lower than the seed disc (the click was on a bright speck), the level is recomputed with the whole-region median so a bright speck cannot shrink the nucleus. A one-pixel binary opening smooths the edge.
5. If the nucleus touches the window edge, the window grows by 1.6 x (up to ±60 µm). A result smaller than (2 µm)² is not used.
6. **If no nucleus is found, a circle is placed** (radius 5 µm, or the typical nucleus radius when nuclei exist). Check such ROIs (or Undo and click again / draw by hand).

**Whole cell** (`draw_cell`, `_cell_region`, `compartments.cells_from_channel`):

1. A window of ±45 µm around the click (±80 µm if the cell is cut off by the window) is block-averaged to about 0.5 µm per pixel.
2. Brightness-independent foreground: the background (a 30 µm minimum filter of the lightly smoothed image, then a 15 µm Gaussian) is subtracted, the result divided by its robust noise and log-scaled (`log(1 + signal/noise)`), smoothed (1.5 µm) and thresholded with **Otsu's method**; closed (1.5 µm), holes filled, objects under 20 µm² removed.
3. Touching cells are separated by a **watershed** along the dim lines between them (on the image smoothed with 1 µm), seeded by your nucleus ROIs where there are any, otherwise by each cell's core (pixels at least 0.6 x the maximum distance from the cell's edge).
4. The cell under the click (or the nearest within 6 µm) is taken, holes filled.

**Cytoplasm** (`draw_cytoplasm`): the whole cell as above **minus its nucleus**: your nucleus ROI(s) in this cell if they cover at least 3% of it; otherwise the dark hole the cell region skipped (if at least 3% of the cell); otherwise the dark core (pixels below the 25th percentile of the cell's smoothed brightness, the most central such piece, holes filled, accepted if 5 - 60% of the cell). The nucleus is widened by 0.5 µm before it is removed; if less than 10% of the cell would remain, the whole cell is used. The outline shown and followed is the whole cell; the measured pixels are the cytoplasm.

**Mitochondria** (`draw_mito`, `mito_pieces`, `mito_envelope`):

1. The cell region is found as for a whole cell (with the mitochondrial network's dark nuclear hole as the cell's seed).
2. Inside it, the image is lightly smoothed (σ = 0.08 µm, at least 0.6 px) and **white top-hat** filtered with a disc of radius 0.8 µm (structures thinner than about 1.6 µm are kept, the diffuse cytosolic haze removed). Noise = robust noise of the top-hat outside the cell.
3. **Mitochondria pixels** = top-hat above both **`mito_k` (3) x noise** and the cell's own Otsu threshold of the top-hat, **plus dense clusters**: pixels brighter than the cell's own Otsu split of log intensity (above background + 5 x noise) that are still textured (top-hat > 2 x noise). In a dim cell with none, the top-hat > k x noise alone.
4. Pieces smaller than 0.1 µm² (and 3 px) are removed.
5. The outline shown and followed is the region within 1 µm of the pieces (closed, holes filled, within the cell); **only the mitochondria pixels are measured**, never the space between them.

**Drawn by hand** (`from_outline`): your polygon. Cytoplasm: minus your nucleus ROIs (widened by 0.5 µm); mitochondria: the mitochondria pixels inside it (as above); others: the polygon itself.

**Resize by scrolling** (`resize_roi`, `fit_area`): each notch changes the area by a factor of 1.12 (`RESIZE_STEP`), with no limit. The new outline is the threshold level of the smoothed image (σ per compartment, `SIGMA_UM`) between the local background (20th percentile of a 4 µm ring) and the ROI's inside (median) that gives exactly that area around the ROI's core; beyond the image's own range (or where two blobs merge at one level) the nearest outline is grown or shrunk evenly to the area. Other cells' pixels are never taken.

**Add to cell** (`extend_roi`): within 6 µm of the click, the image is outlined at the ROI's own edge level (or 0.85 x the clicked pixel's relative brightness, if dimmer); the piece holding the click is joined to the ROI (by a band as wide as the piece, at least 1.5 µm, if they do not touch), holes filled. Other cells' pixels are never taken.

**Merge** (1.2; `roimerge.merge_rois`, `roimerge.merge_cells`): two ROIs of one compartment, of two cells, become one ROI of the first cell. Each ROI's filled shape is used (for cytoplasm and mitochondria, the followed region). The two must be next to each other: the number of empty pixels between them may be at most 3 µm (`MAX_GAP_UM`), and never less than 3 px whatever the pixel size (`MIN_GAP_PX`); further apart, the merge is refused. The merged shape is the union of the two plus the smallest bridge that makes them one 4-connected piece: a morphological closing (dilation, then erosion) of the union with a growing radius r = 1, 2, 3 ... px, whose new pixels are kept only in the region between the two ROIs (pixels p with dist(p, A) + dist(p, B) ≤ gap + 1 + 2r) and never on a pixel of another cell's ROI; the smallest r that joins them is used. If no radius up to ⌈max gap / 2⌉ + 2 joins them without another cell's pixels (another cell lies between them), the merge is refused. Holes that the join closes in are filled, except pixels of another cell; each ROI's own holes stay holes (e.g. the nucleus inside a cytoplasm outline). Measured pixels: for nucleus and whole cell, the merged shape; for cytoplasm, both ROIs' measured pixels plus the bridge outside the nucleus; for mitochondria, only both ROIs' mitochondria pixels (the bridge is not mitochondria). The work is done in a box padded beyond the image, so ROIs at the image edge merge too. Because a cell holds one ROI per compartment, **every compartment both cells have is merged the same way**, in the order nucleus, whole cell, mitochondria, cytoplasm; if one of them cannot be merged (e.g. two nuclei that are not next to each other) the whole merge is refused, naming that compartment. A compartment only the second cell has comes along; after a nucleus merge the merged cytoplasm's measured pixels leave out the merged nucleus. The merged ROI keeps the first ROI's channel; the second cell's number is no longer used (the other cells keep their numbers). Its include / exclude choice and tracker boundary lines are dropped (except the choice for a compartment it brings along). Merging clears the tracking; Undo restores both cells. A merge is not counted as an ROI drawn by hand (for Smart auto-select, section 6.15). The methods text's *Regions of interest* paragraph says that each outline "could be resized, split, merged, extended or drawn by hand where needed" (1.2 added *merged*).

**Split** (`split_roi`): the drawn line (2 px wide, its ends continued straight) cuts the ROI; the two largest pieces must each hold at least 5% of the ROI (and 9 px); every other pixel goes to the nearer piece. The piece that overlaps the cell's other ROIs (e.g. its nucleus) stays with the cell; the other becomes a new cell.

**Which cell an ROI belongs to** (`link_cell`): a new ROI joins a cell that does not yet have this compartment if it touches (within 1 µm) one of that cell's ROIs; otherwise the nearest cell whose ROI centre is within half the sum of the two ROIs' equivalent diameters plus 3 µm; otherwise it becomes a new cell. Right-click to correct.

**No shared pixels** (`cut_overlaps`): a new ROI loses the pixels of the same compartment's ROIs of other cells (the largest remaining piece is kept). A clicked or hand-drawn ROI with less than 30% left is refused ("already covered").

### 8.3 AUTO-DETECT criteria

AUTO-DETECT (`manual.auto_select`) is conservative on purpose: it proposes only the obvious objects, and you review them. Objects within 2 µm of the image edge are never proposed; existing ROIs are never duplicated.

**Nuclei** (`_auto_nuclei`):

1. Candidates: nucleus-sized blobs - local maxima (6 µm neighbourhood) of a difference of Gaussians (σ 1.5 µm minus σ 5 µm) above 6 x its robust noise; up to 3000, brightest first.
2. Each is outlined like a click (section 8.2; windows ±25 µm, then ±45 µm).
3. Touching nuclei (two or more blob centres in one outline with solidity < 0.85) are split by a watershed, only if every part is at least 30 µm² with solidity ≥ 0.85.
4. Kept if **30 - 1000 µm²** and **solidity ≥ 0.80**.
5. "Obvious" relative to this image: the lift (inside - local background) must be at least 3 x the local noise and at least 1.5% of the 90th-percentile lift of all candidates; the outline must be smooth (circularity 4πA/P² ≥ 0.6, or ≥ 0.7 for dimmer nuclei with lift < 8% of that 90th percentile, which must also have solidity ≥ 0.88). Finally fragments smaller than 30% of the median accepted area are dropped.

**Whole cells, cytoplasm, mitochondria**: one candidate beside each of your nuclei that has no ROI of this compartment yet (the brightest of 16 points on a circle at 1.5 x the nucleus radius); without nuclei, the bright spots of the channel (smoothed 4 µm, at least 12 µm apart, above the median + 8 x noise; up to 600). Each is drawn like a click and kept if **60 - 8000 µm²**, **signal-to-noise ≥ 5** (mean inside minus the 25th percentile of a 3 µm ring, divided by the image background noise) and at least 70% of it is left after trimming other cells.

Under an IF rule, proposals that fail the gate are skipped.

**Brightness slider** (V2.5, `gui/clickwin.py`: `_auto_brightness`, `_auto_apply`). The proposals of one AUTO-DETECT press are ranked by **brightness = (sum of the detection image's pixels inside the ROI / number of pixels) - mean of the background region's pixels on the same image**, at the timepoint shown. The detection image is the image the compartment is drawn on (channel A's raw pixels; the combined image under WITH). The slider (range 1 - number found, starting at all) keeps the N brightest: moving it re-places the N brightest proposals (in rank order, each trimmed against the cells already there exactly as at the first press) on top of the cells as they were before AUTO-DETECT, so the dimmest are removed first. The label shows the brightness of the dimmest one kept, in counts above background.

**Display only: smooth playback** (V2.9, `gui/frames.py`). For movies of 1600 px or more on a side, the background readers also make a half-size copy of each frame (the mean of each 2 × 2 block of pixels, rounded) which the image shows while the whole image is on screen at less than one screen pixel per copy pixel; as soon as you zoom in, the full frame is shown. While playing, the graph's time line moves about six times a second. Nothing is ever measured on the copy: every ROI, measurement and export uses the raw frames. **V3.0: the frame you are on is read first.** Two background readers always take the waiting frame nearest the current timepoint (ahead before behind) and skip frames you only passed over (more than 4 behind or 16 ahead). Before, dragging the slider queued a read for every timepoint passed over and the frame you stopped on was read last: on a 4-channel 2400 × 2400 movie on the lab's D: drive (~0.25 s per frame not yet in memory) it appeared 12.2 s after a drag across 60 frames; now 0.6 s. Closing the window now waits for a read in progress before the `.nd2` is closed (closing it under a reader could crash the app on closing: *Windows fatal exception: access violation*).

### 8.4 Background region

The background is measured in **one region per movie, at every timepoint**. Since V2.5 the region **includes cells**: what is subtracted is the light of the dish and the medium **and the autofluorescence of non-transfected cells** in the region. **Every pixel of the region is used at every timepoint - nothing is left out** (`manual.BackgroundMeter`, method label `all pixels, object check v2.7`; V2.5 / V2.6: `all pixels, fluctuation check v2.5` - the same numbers, only the warning differs). The background of a timepoint and channel is

**background mean = (sum of the raw values of all the region's pixels) / (number of pixels in the region)**,

and this is subtracted from every ROI of that channel and timepoint (section 8.7). It is computed from all of the region's raw pixels (no subsampling, no smoothing); frames may arrive in any order (the tracker goes forwards, then backwards).

**Fluctuation check** (`manual.background_fluctuation`, after tracking; constants in `manual.py`). A bright, dead or passing cell in the region shows up as a jump in the background trace, a region that changes over the movie as a drift. For each channel:

1. **trend** = the running median of the background over **5 timepoints** (`BG_FLUCT_WIN`, centred; shorter at the first and last timepoints); **jump** = background - trend;
2. a timepoint is **flagged** when its |jump| is **both** more than **5 robust SD of the jumps** (`BG_FLUCT_K`; robust SD = 1.4826 x the median absolute deviation, MAD, of all the channel's jumps) **and** more than **5% of the background level** (`BG_FLUCT_REL`; level = the median of the channel's background trace);
3. **drift** = (largest - smallest trend) / level; reported when more than **20%** (`BG_DRIFT_REL`).

Channels with fewer than 5 measured timepoints are not checked. The check also notes when measured ROIs (the followed regions of the tracked cells) lie inside the region, and the largest fraction of the region they cover at one timepoint - their pixels are used, like every pixel. **Jumps and drift are recorded (Settings sheet, methods text) but, since V2.7, not warned about**: lamp flicker, focus changes and bleaching change the cells as much as the background, and in the lab's movies they set the warning off when nothing had entered the region.

**Object check (V2.7, the warning)** (`manual.bright_share`, `background_objects`). At every timepoint and channel, the share of the background value that comes from **very bright pixels** - above both the region median + 10 robust SD and 2 × the median of that timepoint's raw region pixels (the same 'very bright' level as for placing the region) - is

**bright share = Σ (pixel − median) over the very bright pixels / (number of region pixels × median)**,

i.e. how much they raise the background mean, as a fraction of the level. A timepoint is flagged when its bright share is more than **3% of the level** (`BG_OBJ_REL`) above that channel's median bright share over the movie - a bright or dead cell floating into the region. Measured cells covering **more than 5%** of the region (`BG_ROI_WARN`) are flagged too (a few overlapping pixels are not). Only then a box **Object in the background region** lists it (`manual.background_warning`; for the automatic region as well as for yours), with **Redraw background** (switches to Compartment *Background* > *Draw by hand*; draw a new region and press TRACK & MEASURE again) and **Keep it**. **The check never changes a value.**

**Recorded** per timepoint and channel: the background mean (`background`), the pixel SD of the region's pixels (`background_sd`, population SD; used by QC), their sum (`background_sum`), and per timepoint the number of pixels used (`background_npx`, = the region's pixel count); plus the region's size, the fraction of it covered by measured ROIs at each timepoint, and per channel the fluctuation check (level, flagged timepoints, largest jump and drift as fractions of the level) with its constants (`track["background"]`).

**Where the region is**:

- **Automatic** (`manual.auto_background`): a **large square, 150 µm** (`background_max_um`, default 150) that may hold non-transfected cells. It is placed on a block-averaged copy of about 600 px (block size f = max(1, ⌊min(H, W) / 600⌋)) using the first, middle and last timepoints: a pixel is forbidden if, in any channel on any of these timepoints, its smoothed (σ = 1 px, `BG_SMOOTH_PX`) value is very bright: above **both** the frame's median + **10 robust SD** (`BG_BRIGHT_K`) **and** 2 x the median (`1 + BG_BRIGHT_REL`), computed over the whole (block-averaged) frame; forbidden pixels are widened by 1 µm (`BG_HALO_UM`). When the movie opens no ROI exists yet; **just before tracking the automatic region is placed again, now also avoiding every ROI you drew, widened by 2 µm** (`BG_ROI_MARGIN_UM`). A placement is valid if the square is at least 5 µm from the image edge, holds **no ROI pixel at all** and is **at least 90% free** of bright objects (`BG_AUTO_FREE`). Among the valid places the freest is used (ties: nearest the image centre). If no place fits, the square shrinks by 15% per step down to **25 µm** (`BG_AUTO_MIN_UM`); if even that fails, you are asked to draw it by hand. The region is the whole square, and every pixel of it is measured: the bright objects only decide where it is placed.
- **A square where you click** (Compartment *Background* > Add, or right-click > *Put the background region here*, `background_at`): a **60 µm** square (`BG_HAND_UM`) centred on the click, clipped at the image edge - cells included.
- **Drawn by hand** (Compartment *Background* > Draw by hand, `background_from_outline`): your freehand outline (at least 16 pixels) - cells included.

**Tracking made before V2.5** keeps its own background values: one fixed mask (the region without the pixels that were bright when it was placed) at every timepoint (section 7). **Sessions tracked with the earlier V2.5 method** (very bright objects - the thresholds above -, fast-moving objects and the measured ROIs + 2 µm left out at every timepoint, method label `per-timepoint exclusions v2.5`) keep their values, and their Settings sheet and methods text describe that method.

### 8.5 The tracking algorithm

`manual.track_cells` (tracker label `redraw-every-frame v2.5 (rules locked to ONLY, hard size limits)`). Each cell is followed from the drawn timepoint `t0` forwards to the last timepoint, then from `t0` backwards to the first. Within a timepoint, compartments are processed in the order nucleus, whole cell, cytoplasm, mitochondria (the others need the nuclei of the same timepoint). **Every image used for moving and outlining is the raw plane of the rule's channel A** of that timepoint, whatever the mode (V2.5 rule lock, section 6.3); WITH and AND only trim the measured pixels afterwards (step 7); measurements always use the raw stack.

**0. Edge level, from the drawn timepoint** (`_edge_level`). For each ROI: a window 10 µm (`EDGE_PAD_UM`) larger than the ROI is smoothed with a Gaussian of σ = `SIGMA_UM` (nucleus 0.6 µm, whole cell 1.0 µm, cytoplasm 1.0 µm, mitochondria 2.0 µm; at least 0.8 px, `SIGMA_MIN_PX`). Local background = 20th percentile (`RING_BG_PCT`) of a 4 µm ring (`RING_UM`) around the ROI's followed region; inside = median within it; edge = median on the region's boundary pixels. **Edge level = (edge - background) / (inside - background)**, limited to **0.12 - 0.8** (`EDGE_LEVEL_CLIP`). It says where the outline sits between background (0) and inside (1), so the redraw follows brightening and dimming alike.

**1. Movement** (`_sub_shift`). For each cell, the image around its ROI of the lead compartment (the first rule's; else the next compartment it has) - the ROI's box plus the search margin plus 8 px (`SHIFT_PAD_PX`) - is compared between the previous and the current timepoint by **phase cross-correlation** (scikit-image `phase_cross_correlation`, the method of Guizar-Sicairos et al. 2008; upsampling factor 10 = 0.1 px precision, `PHASE_UPSAMPLE`; mean-subtracted, unnormalised). The shift is limited to ± the search margin **`margin_px` = max(3 px, `max_move_um` = 3 µm in pixels)** (`MARGIN_MIN_PX`). Shifts are summed with sub-pixel precision (a running remainder, so slow drift is never rounded away), and all of the cell's ROIs are moved by the whole-pixel part.

**2. Redraw** (`_redraw`). Around the moved ROI (window = ROI box + margin + 4 µm), the frame is smoothed (σ as above) and **thresholded at background + edge level x (inside - background)**, with background = 20th percentile of the 4 µm ring around the moved ROI (excluding neighbours and walls; if the ring has fewer than 20 pixels, the 10th percentile of the window) and inside = median within the moved ROI. Only pixels within the margin of the moved ROI are allowed. Connected pieces are kept if at least 5% (`MIN_HIT_FRAC`) and 3 pixels of the moved ROI fall in them; holes are filled.

**3. Neighbours, walls and boundary lines.** Pixels nearer another cell's (moved) ROI of the same compartment than to this one belong to that cell, and its own pixels are never taken (**rivals**); for whole cells, cytoplasm and mitochondria, the other cells' nuclei of the same timepoint are never included (**walls**). **Tracker boundary lines** (V2.5, `wall_mask`, `boundary_side`): each line of a cell (a polyline in image coordinates) is rasterised and thickened to 3 px (`WALL_HALF_PX = 1`, a 3 x 3 dilation, so no region can pass through a diagonal gap); the image outside the lines is split into 4-connected parts, and the cell may only use **the part that holds most of its drawn ROI** (of its lead compartment; if the ROI lies on the line itself, the part nearest its centroid). This part is computed once, before tracking, and is fixed in the image; only pixels inside it are allowed in steps 2 - 4.

**4. Size guard.** The redrawn area must lie within **[max(0.67 x A_prev, (1 - tol) x A_drawn), min(1.5 x A_prev, (1 + tol) x A_drawn)]**, where A_prev = the moved previous outline's area (`AREA_STEP = (0.67, 1.5)`), A_drawn = the area you drew and **tol = `size_tol` = 0.25** (the *Size may change by* setting, 0 - 1). (If the two ranges do not overlap, the previous area clipped to the drawn range is the target.) Outside that, the outline is **re-fitted** (`fit_area`): the threshold level between 0.02 and 0.98 that gives the nearest allowed area around the ROI's core (the moved ROI eroded by 1 µm) is found by bisection (up to 16 steps, to within max(2 px, 1%)); where the image jumps (two blobs merging at one level) or the area is beyond the image's own range, the nearest outline is grown or shrunk evenly to exactly that area, never into other cells. The re-fitted outline is accepted only within 0.95 - 1.05 x the allowed range (`REFIT_ACCEPT`); **its level then replaces the ROI's edge level for later timepoints** (adaptive edge level).

**4b. Hard size limits** (V2.5, `size_limits`, `_exact_area`, `_grow_bright`). After step 4, the accepted outline must have between **n_lo = ⌈(1 - tol) x A_drawn⌉** and **n_hi = ⌊(1 + tol) x A_drawn⌋** pixels (n_lo at least 1; tol = 0 gives n_lo = n_hi = A_drawn, **exactly the drawn pixel count**). There is no slack:

- **too many pixels** → the n_hi brightest **connected** pixels around the outline's middle: the middle is its deepest point (maximum of the distance transform); the highest smoothed-image level whose connected piece holding the middle still has ≥ n_hi pixels is found by bisection over the outline's own pixel values, and the piece of the next level up is grown inside it, one ring of 4-connected neighbours at a time, brightest pixels first, to exactly n_hi pixels. (If the outline is in several pieces and the middle piece has fewer than n_hi pixels, the middle piece is kept whole and the brightest pixels of the other pieces are added.)
- **too few pixels** → grown from the outline by repeatedly adding the brightest (smoothed) 4-connected neighbouring pixels until n_lo pixels, **only into allowed pixels** (never another cell's, never a wall, never across a boundary line); if there is no more room it stays smaller.

On the drawn timepoint the limits use tol = min(0.10, `size_tol`) (step 6). The limits apply to the **followed region** (the whole cell for cytoplasm, the envelope for mitochondria); the measured pixels of step 7 can be fewer.

**4c. No overlaps** (V2.5, `_resolve_overlaps`). After all cells of a compartment are redrawn in a timepoint, regions are processed in the order: redrawn ones first (quality 1), then the fallback ones of step 5, each by cell number. Each region loses any pixel on the far side of its boundary lines and any pixel already held by a region processed before it (redrawn regions are already disjoint by step 3; ties between fallbacks: the lower cell number keeps the pixel), and keeps its largest piece (the one holding its deepest point). If nothing is left, its region of the previous timepoint is used, trimmed the same way. A trimmed region with fewer than n_lo pixels is grown back by its brightest neighbouring pixels (as in 4b, on its own smoothed image, never into another cell or across its lines). So **no two cells' ROIs of one compartment share a pixel at any timepoint**.

**5. Rejection.** If no acceptable outline is found, or less than half of the new outline lies inside the moved previous outline (`MIN_OVERLAP_PREV = 0.5`), the **moved previous outline is used** for that timepoint and it is flagged (quality 0.3); step 4c then applies to it.

**6. The drawn timepoint** is outlined by the same method (from your outline, on channel A - the image you drew on, except under WITH, where you drew on the combined image), but within **±10%** of what you drew (`FIRST_FRAME_TOL`, the smaller of 0.10 and `size_tol`; a hard limit since V2.5, step 4b); if that fails your outline is kept (quality 0.9; step 4c still applies to it). So every timepoint is outlined by one method.

**7. Compartment specifics** (`_finish`). **Cytoplasm**: the followed region is the whole cell; at every timepoint the cell's nucleus ROI of that timepoint (widened by 0.5 µm) is removed - or, for a cell without a nucleus ROI, the dark hole of the drawn cytoplasm, moved with the cell; if less than 10% would remain, the whole region is measured. **Mitochondria**: the followed region is the mitochondria envelope; at every timepoint the mitochondria pixels inside it are found again (section 8.2, threshold `mito_k` x noise), so moving, fusing and splitting mitochondria are followed; if none are found at a timepoint, the whole region is measured at that timepoint. **AND rules**: the measured pixels are those also bright in channel B (section 6.3). **WITH rules**: the measured pixels are those where the combined image is above the outline's frozen edge level on it (section 6.3). Under AND and WITH the followed region itself stays whole (it is what the next timepoint is followed from and what neighbours are kept away from); a timepoint with no pixel left measures NaN (quality 0.3).

**Quality per ROI and timepoint**: 1.0 = redrawn; 0.9 = drawn timepoint, your outline kept; 0.3 = moved outline used (or, under AND / WITH, no pixel left). The fraction of ROI-timepoints with quality ≥ 0.9 is reported as "redrawn" after tracking and in the methods text.

**IF gate**: computed per cell on the drawn timepoint, after its redraw (section 6.3).

**Background**: measured at every timepoint by `BackgroundMeter` as the frames come (section 8.4), from every pixel of the region; the measured ROIs of that timepoint are only counted (for the note), not left out.

Every tracking constant is returned with the result (`out["params"]`, built by `manual.track_params`; V2.5 adds `size_limits`, `rule_lock`, `wall_px`, `boundaries` (per cell number, 1-based: the lines' image coordinates) and `background` (every background constant)) and written into every export (Settings and Methods sheets, methods text, ROI and session files).

### 8.6 Measurement

At every timepoint, for every ROI (`manual._measure`), from the **raw, full-resolution pixels under the final ROI mask**, for **every channel**:

- **sum** = the raw counts of every mask pixel added up (64-bit floating point - exact for integer counts);
- **area** = number of mask pixels (cytoplasm: without the nucleus; mitochondria: the mitochondria pixels only; AND / WITH: the kept pixels only);
- **mean intensity = sum / area**;
- **saturated pixels** = number of mask pixels at or above the saturation level.

An ROI with no pixels gives NaN. The background is measured in the same way from all the region's pixels (sum / number of pixels, section 8.4). Since V2.5 the sums and areas are written to the workbook (sheets `Sum_<channel>`, `Area_px`, `Area_um2`, section 9.2), so every mean can be checked: Raw = Sum / Area_px for the same cell and timepoint.

### 8.7 Background subtraction, ratios, F/F0 and R/R0

For cell *k*, channel *c*, timepoint *t* (`measure.Measurements`; the Excel sheets use the same arithmetic as live formulas):

- **Background-subtracted intensity** `F(t) = ROI mean(t) - background mean(t)` of the same channel and timepoint, with ROI mean = sum / pixel count of the ROI and background mean = sum / pixel count of the background pixels left at that timepoint (section 8.4). The subtraction is done first; F/F0 and the ratios are calculated from the background-subtracted values.
- **Ratio** `R_A/B(t) = F_A(t) / F_B(t)` - for **every ordered pair** of channels (A/B and B/A). A non-finite result (e.g. division by zero) gives no value.
- **F/F0** `= F(t) / F(t_baseline)` and **R/R0** `= R(t) / R(t_baseline)`, with `t_baseline` the baseline timepoint (time 0). A missing or zero baseline value gives no value for that cell. (A negative baseline value is not blanked: inspect cells whose background-subtracted baseline is near or below zero - QC notes them, section 8.11.)
- **Ratio check** (V3.0, `Measurements.ratio_checked` / `ff0` / `rr0`; *Ratios need baseline ≥ × noise* in step 4, default **5**, 0 = off): dividing by (almost) nothing gives meaningless numbers, e.g. untransfected cells in a sensor ratio or a cell that fades. The noise of an ROI's mean is `σ = background pixel SD(t) / √(ROI pixels(t))`. A cell's **F/F0** is left out (blank) when `F(t_baseline) < k·σ`; its **ratio** and **R/R0** when either channel is below `k·σ` at the baseline, and single ratio values where the denominator falls below `k·σ` at that timepoint. Left-out values are blank in every graph, table and workbook, so means and n skip them; the trace panel says how many included cells have no value for the quantity shown, and the methods text states the rule. In the workbook the noise is on the `Noise_<ch>` sheets and k is **MinSNR** on the Settings sheet (change it there and every sheet follows). Results tracked before V2.2 (no pixel SD recorded) are not checked. On the lab's U2OS movie (96 nuclei, R/R0 GFP/Cy5) this took the largest R/R0 from 678 to 18 and the mean at the last frame from 2.30 to 2.09, leaving out 4 cells and 61 single values.
- **Time** = (timepoint - baseline timepoint) x frame interval, in minutes (or in timepoints when the interval is unknown); earlier timepoints are negative.

### 8.8 Statistics

Over the **included** cells at each timepoint, using only the cells that have a value there (`graphstyle.describe` - the one implementation used by the trace panel, the graphs and the CSV files):

- **n** = number of included cells with a finite value at that timepoint;
- **mean** = arithmetic mean;
- **SD** = sample standard deviation (denominator n - 1);
- **SEM** = SD / √n;
- **95% confidence interval** = mean ± t(0.975, n - 1) x SEM (Student's t, `scipy.stats.t`);
- SD, SEM and CI are not defined (blank) when n < 2.

The Excel workbook computes the same mean, SD (`STDEV`, n - 1), SEM and n with live formulas from the Include sheet. The `.prism` and `.pzfx` "mean, SEM, n" tables use the same definitions; in the `.prism` graph, Prism itself draws the mean ± SEM from the cells-as-replicates table.

**Replicate averaging across dishes** (Compare / average runs, `compare.group_line`, `compare.align`; section 6.10). One run = one dish = one experimental unit.

1. **Per dish and timepoint: the dish mean** = the arithmetic mean of that dish's **included** cells that have a value there, made from the run's own export numbers (background-subtracted, from its own baseline - or the common baseline you set), with `graphstyle.describe` as above.
2. **Per group and timepoint: across the dish means** - **mean** of the dish means; **SD** with denominator n - 1; **SEM = SD / √n**; **95% CI = mean ± t(0.975, n - 1) x SEM**; **n = number of dishes** with a value at that time. Every dish counts once, whatever its number of cells. SD, SEM and CI are blank when n < 2.
3. **Pooled cells** (written too, for reference): every included cell of every dish of the group as one sample - mean, SD (n - 1), SEM = SD / √(n cells), n = cells. Cells of one dish are not independent replicates (pseudo-replication), so **the dish-mean statistic is the one to report**; the pooled SEM is smaller only because n counts cells.
4. **Time alignment**: each dish's time counts from **its own** baseline (time 0), in minutes from its own frame interval (in timepoints if any interval is unknown). Only the times of the first dish that **every** dish of the group also has are used: a time matches when a dish has a time within **0.1% of the shortest frame interval** of the group (i.e. the same frame time; in timepoints: exactly equal). **Nothing is interpolated.** Dishes imaged at different intervals (e.g. 30 s and 60 s) keep only their common frame times; dishes of different lengths keep their common part; the window and the methods text say how many timepoints of each dish were left out. A dish without included cells is left out of the group and named.

The per-dish table (each dish's mean, SEM, SD and n over its own cells at every common time) is written with every group comparison, so the group numbers can be recomputed by hand.

### 8.9 Graph look

The PNG / SVG graphs and the *As exported* view are drawn from the same data and statistics (mean, and SD, SEM or 95% CI as chosen; bars or band; optional thin line per included cell). The default look matches the built-in Prism template (V2.5: mean line 0.59 pt in #28D2F0, filled circles 4.32 pt, capped SEM error bars, no cell lines, 18 pt axis titles, tick labels 0.9 x that, Arial, 6 x 4.5 inches; PNG at 300 dpi = 1800 x 1350 pixels). (Up to V2.4: black 1 pt line, 3 pt circles, 12 pt axis titles.) The look never changes a number. Since V2.4 the same look is written into the `.prism` graphs (section 9.4), so the PNG, the live view and Prism agree, except for the few looks Prism cannot draw.

### 8.10 Baseline drift

Per cell and quantity: the **slope of the least-squares straight line** (`numpy.polyfit`, degree 1) through timepoints `drift_from` - `drift_to` (default 2 - 9, inclusive) against time in minutes (per timepoint if the interval is unknown); at least 3 valid points are needed, otherwise no value. The drift window must span at least 3 timepoints to be exported. Units: quantity per minute.

### 8.11 Quality control

After tracking, every cell is checked for **technical** problems only (`qc.run_qc`, `qc.qc_cell`) - never for the size or direction of its response (unless you switch on the optional responder check). In the click workflow **QC never excludes a cell by itself**: every ROI was drawn or approved by you, so QC writes notes (cell list, QC_report sheet) and you decide. The one exception is the IF rule, which excludes cells without signal in channel B because that is what the rule asks for (you can include them again).

| Test | Note added when | Default (setting) |
|---|---|---|
| Not redrawn | the moved outline was used (quality < 0.4) at more than this fraction of timepoints | 0.20 (`qc_max_lost_frac`) |
| Empty ROI | the ROI had no pixels at any timepoint | - |
| Outline jumped | the area changed by more than this factor between consecutive timepoints | 2.0 (`qc_max_area_jump`) |
| Too dim | median background-subtracted signal / median background pixel SD < this, in the rule's channel A | 3 (`qc_min_snr`) |
| At or below background | the median background-subtracted intensity is ≤ 0 in a channel the rule uses (A, and B for WITH / AND / IF) | - |
| Saturated | more than this fraction of the ROI's pixels at the saturation level, in any channel at any timepoint | 0.02 (`qc_max_saturated_frac`) |
| Touched the image edge | the ROI's box touched the image edge at any timepoint | on (`exclude_border`) |
| One-frame artefact | a value more than this many robust SD (the robust SD of the frame-to-frame differences / √2) and more than 20% of the trace's median level away from both neighbours while the neighbours agree, in any channel, at a timepoint where the outline also changed by more than 25% from its neighbours or was not redrawn; timepoints where at least a quarter of the cells (and at least 3) jump together are ignored as field-wide | 6 (`qc_spike_sigma`; 0 = off) |
| Small speck | the ROI on the drawn timepoint is smaller than this fraction of the median ROI area | 0.35 (`qc_min_area_frac`; 0 = off) |
| No response (optional, off by default) | the 3-point median-smoothed F/F0 or R/R0 of the key quantities never leaves 1 ± this after the baseline | 0.10 (`resp_enabled = false`, `resp_threshold`, `resp_direction`, `resp_quantity`) |
| IF gate | signal-to-noise in channel B on the drawn timepoint < `gate_snr` - **excludes the cell** | 5 (`gate_snr`) |

### 8.12 Parameter reference

All parameters, their defaults and where they are set. The values actually used for an export are always listed in the workbook's Settings and Methods sheets and in the methods text - check them there, because `settings.json` may carry values over from an earlier version.

**Set in the windows**

| Parameter | Default | Unit | Set in | Code name |
|---|---|---|---|---|
| Pixel size | from the file | µm/px | start screen | `Experiment.um_per_px` |
| Frame interval | from the file | s | start screen | `Experiment.seconds_per_frame` |
| Channel names | from the file | - | start screen | `Experiment.channels` |
| Tracking rules | `Track nucleus using <channel 1> ONLY` | - | step 1 | `Settings.track_rules` |
| ROIs drawn on timepoint | the first timepoint you click on | 1-based | step 2 | `t0` (stored 0-based) |
| Size may change by | ±25% (0 - 100%, steps of 5; 0 = exactly the drawn pixel count) | fraction of drawn area (hard limit) | step 3 | `Settings.track_size_tol = 0.25` → `size_tol` |
| Tracker boundary lines | none | image px (x, y) per cell | step 3 *Tracker boundary* | `boundaries` (session / ROI file state; `track_params`) |
| Background region | automatic 150 µm square | - | step 2 (Compartment *Background*: Add = 60 µm square, Draw by hand = freehand) | `bg_kind` = `auto` / `click` / `hand` |
| AUTO-DETECT keep | all found | number of cells | step 2 slider after AUTO-DETECT | (not saved; the ROIs placed are) |
| Baseline timepoint | 1 | 1-based | step 5 (and the Excel dropdown) | `Settings.baseline_timepoint` |
| Drift window | T2 - T9 | 1-based | step 5 | `Settings.drift_from`, `drift_to` |
| Graph look | Prism default - mean ± SD (V3.0; SEM before) | - | Traces panel, As exported | `Settings.graph_style` |
| Automatic saving | on | - | File menu | `Settings.autosave_sessions` |
| Offer earlier analyses | on | - | File menu / dialog | `Settings.ask_previous_runs` |
| Largest movement | 3.0 µm | µm | Step 3 *Max movement between timepoints* | `Settings.max_move_um` |
| IF gate | 5.0 | x noise | Step 3 *IF rule: needed signal* (shown with an IF rule) | `Settings.gate_snr` |
| AND threshold | 3.0 | x noise | Step 3 *AND rule: pixel threshold* (shown with an AND rule) | `Settings.overlap_k` |

**Set only in `settings.json`** (`%USERPROFILE%\PeterPiper data\users\<name>\settings.json`, under `"settings"`; edit with Notepad **while PeterPiper is closed**, because it saves its settings on exit)

| Parameter | Default | Unit | Code name | Meaning |
|---|---|---|---|---|
| Mitochondria threshold | 3.0 | x noise | `mito_k` | Top-hat threshold for mitochondria pixels (drawing and tracking). |
| Automatic background, largest square | 150 (V2.5; was 120) | µm | `background_max_um` | Start size of the automatic background square. A value of exactly 120 carried over from an earlier version's settings is changed to 150 once (`bg_v25`); any other value you set is kept. |
| Ratio sheets | true | - | `write_ratio_sheets` | Ratios for every ordered channel pair. |
| Key quantities | `F/F0 - GFP; R/R0 - GFP/Cy5` | - | `resp_quantity` | Shown first in traces, graphs and exports (names missing from a movie are ignored). |
| QC thresholds | see section 8.11 | - | `qc_*`, `exclude_border`, `resp_*` | Notes only. |

**Fixed in the code - tracking** (`manual.py`)

| Constant | Value | Meaning |
|---|---|---|
| `SIGMA_UM` | nucleus 0.6, whole cell 1.0, cytoplasm 1.0, mitochondria 2.0 µm | Gaussian σ before outlining while tracking (and resizing). |
| `SIGMA_MIN_PX` | 0.8 px | Smoothing never below this. |
| `RING_UM`, `RING_BG_PCT` | 4.0 µm, 20th percentile | Local background ring for edge levels and redraws (not the subtracted background). |
| `EDGE_PAD_UM` | 10 µm | Window around an ROI for its edge level. |
| `EDGE_LEVEL_CLIP` | 0.12 - 0.8 | Limits of the edge level. |
| `AREA_STEP` | 0.67 - 1.5 | Allowed area change vs the previous timepoint. |
| `FIRST_FRAME_TOL` | 0.10 | Size tolerance on the drawn timepoint (smaller of this and `size_tol`). |
| `REFIT_ACCEPT` | 0.95 - 1.05 | Slack for accepting a re-fitted outline. |
| `MIN_OVERLAP_PREV` | 0.5 | At least half of a new outline inside the moved previous one. |
| `MIN_HIT_FRAC` | 0.05 (and ≥ 3 px) | Pieces kept in a redraw. |
| `MARGIN_MIN_PX` | 3 px | Minimum search margin. |
| `SHIFT_PAD_PX` | 8 px | Extra border of the phase-correlation window. |
| `PHASE_UPSAMPLE` | 10 | Phase-correlation upsampling (0.1 px). |
| `fit_area` levels | 0.02 - 0.98, ≤ 16 bisection steps, tolerance max(2 px, 1%), even grow / shrink if > 3% off | Size-guard re-fit and resize. |
| `size_limits` | ⌈(1 - tol) x A_drawn⌉ - ⌊(1 + tol) x A_drawn⌋ px (≥ 1) | V2.5 hard limits on the followed region (`_exact_area`: brightest connected pixels / brightest 4-connected neighbours). |
| `WALL_HALF_PX` | 1 (lines 3 px thick) | Tracker boundary line thickness (`wall_px` = 3). |
| rule lock | `ONLY outline on channel A` | Every rule follows on channel A's raw pixels (`rule_lock`). |
| `RESIZE_STEP` | 1.12 | Area factor per scroll notch. |
| `TRACKER` | `redraw-every-frame v2.5 (rules locked to ONLY, hard size limits)` | Tracker label recorded in exports (`redraw-every-frame v2.3` up to V2.4). |

**Fixed in the code - background** (`manual.py`, recorded as `track_params["background"]`, method `all pixels, object check v2.7`; object rise `BG_OBJ_REL` = 0.03 of the level, cell overlap warning `BG_ROI_WARN` = 0.05 of the region)

| Constant | Value | Meaning |
|---|---|---|
| `BG_FLUCT_K` | 5 robust SD | Fluctuation check: a timepoint is flagged when its jump (background - running median) is more than 5 robust SD (1.4826 x MAD) of the channel's jumps ... |
| `BG_FLUCT_REL` | 0.05 | ... **and** more than 5% of the background level (the median of the channel's trace). |
| `BG_DRIFT_REL` | 0.20 | Drift reported when the running median changes by more than 20% of the level over the movie. |
| `BG_FLUCT_WIN` | 5 timepoints | Running-median window for both tests. The check only informs you; it never changes a value. |
| `BG_SMOOTH_PX` | 1.0 px | Gaussian σ before the very-bright test (placement of the automatic square only). |
| `BG_BRIGHT_K`, `BG_BRIGHT_REL` | 10 robust SD, 1.0 | Very bright (placement only): smoothed > median + 10 robust SD **and** > (1 + 1.0) = 2 x median, any channel, over the whole block-averaged frame. Nothing is left out of the measured region. |
| `BG_HALO_UM` | 1.0 µm | Very bright objects are widened by this when the automatic square is placed. |
| `BG_ROI_MARGIN_UM` | 2.0 µm | The automatic square keeps this gap from the drawn ROIs (measured ROIs inside a region are counted, not left out). |
| `BG_AUTO_MIN_UM`, x 0.85 per step | 25 µm | Smallest automatic square; it shrinks by 15% per step from `background_max_um`. |
| `BG_AUTO_FREE` | 0.9 | The automatic square is ≥ 90% free of bright objects (and holds no ROI pixel); ≥ 5 µm from the image edge; freest place, ties nearest the centre; placed on a ~600 px block-averaged copy of the first, middle and last timepoints. |
| `BG_HAND_UM` | 60 µm | Square placed at a click. |
| hand-drawn minimum | 16 px | Smaller freehand outlines are refused. |

**Fixed in the code - WITH** (`rules.py`)

| Constant | Value | Meaning |
|---|---|---|
| `WITH_MIN_RING_PX` | 20 px | Fewer ring pixels: channel A's frozen background is used. |
| WITH level | the outline's edge level on the combined image at the drawn timepoint (frozen) | Measured pixels: guide > bg + level x (inside - bg); bg = 20th percentile of a 4 µm ring, smoothing = `SIGMA_UM`. |

**Fixed in the code - rules** (`rules.py`)

| Constant | Value | Meaning |
|---|---|---|
| `NORM_STRIDE` | 4 | Every 4th pixel in y and x for the frozen normalisation. |
| `NORM_BG_PCT`, `NORM_TOP_PCT` | 20, 99.5 | Background and bright levels (percentiles). |
| noise | 1.4826 x MAD of the darker half | Frozen per-channel noise. |
| `AND_SIGMA_UM` | 0.5 µm | Smoothing of channel B for AND. |
| `AND_BG_PCT`, `AND_MIN_RING_PX` | 20th percentile, 20 px | Local background of B (4 µm ring). |
| IF signal-to-noise | 6 µm window, 3 µm ring, 25th percentile | Gate measurement (`manual._snr`). |
| `HELP_WEIGHT` | 0.5 | V3.0: each helper channel's weight in the helper image (the main channel's is 1). |
| `HELP_GUARD_UM` | 1 µm | V3.0: a helper-followed outline reaches at most this far beyond the main channel's own outline. |
| helper signal-to-noise | as the IF gate | V3.0: AUTO-DETECT proposes a cell only if every helper is at least *Helper signal needed* (`gate_snr`, 5) × its noise. |

**Fixed in the code - drawing, detection, background** (`manual.py`, `compartments.py`, `segment.py`)

| What | Values |
|---|---|
| Nucleus at a click | window ±25 µm (or 2.5 x typical radius, 15 - 60 µm; grows x1.6 to ±60 µm), σ 0.8 µm, seed within ±2 µm, inside = median of 2.5 µm disc, background = 15th percentile, noise from the darker 40%, contrast > 3 x noise, edge at 0.35, minimum (2 µm)², fallback circle 5 µm radius |
| Whole cell at a click | windows ±45 / ±80 µm, work at ~0.5 µm/px, background 30 µm minimum filter + 15 µm Gaussian, log(1 + signal/noise), 1.5 µm smoothing, Otsu, 1.5 µm closing, ≥ 20 µm², watershed on 1 µm smoothing, nearest cell within 6 µm |
| Cytoplasm | nucleus ≥ 3% of cell, dark core 25th percentile and 5 - 60% of cell, nucleus widened 0.5 µm, ≥ 10% must remain |
| Mitochondria | σ 0.08 µm (≥ 0.6 px), top-hat disc 0.8 µm, k = `mito_k`, dense clusters > background + 5 x noise and top-hat > 2 x noise, pieces ≥ 0.1 µm² and 3 px, envelope 1 µm |
| Linking and overlaps | touching within 1 µm, else centre distance ≤ half the summed equivalent diameters + 3 µm; refused if < 30% left after trimming |
| Merge (1.2, `roimerge.py`) | gap ≤ 3 µm (`MAX_GAP_UM`), at least 3 px (`MIN_GAP_PX`); closing radius 1, 2, 3 ... px up to ⌈max gap / 2⌉ + 2, new pixels only where dist to A + dist to B ≤ gap + 1 + 2r and not on another cell; one 4-connected piece; holes closed by the join filled; compartments merged in the order nucleus, whole cell, mitochondria, cytoplasm |
| AUTO-DETECT nuclei | DoG 1.5 / 5 µm, peaks 6 µm apart > 6 x noise, ≤ 3000; 30 - 1000 µm², solidity ≥ 0.80; lift ≥ 3 x noise and ≥ 1.5% of 90th-percentile lift; circularity ≥ 0.6 (≥ 0.7 and solidity ≥ 0.88 if lift < 8%); ≥ 30% of median area; split parts ≥ 30 µm² and solidity ≥ 0.85; not within 2 µm of the edge |
| AUTO-DETECT cells / cytoplasm / mito | 16 points at 1.5 x nucleus radius, or peaks (4 µm smoothing, 12 µm apart, > median + 8 x noise, ≤ 600); 60 - 8000 µm²; signal-to-noise ≥ 5; ≥ 70% kept after trimming |
| Automatic background | see "Fixed in the code - background" above (150 µm → x0.85 → ≥ 25 µm) |
| AUTO-DETECT slider | rank = mean of the detection image in the ROI - background mean on the same image, at the timepoint shown; dimmest removed first |

### 8.13 Smart auto-select: the method (1.1)

Smart auto-select (`smartselect.learn`, using `detectors.py`) is the trained auto-detect of section 6.13, learned from one bin of movies you hand-picked, without the quiz. Every number below is fixed in the code.

1. **Training movies.** The movies of the chosen bin (one kind of experiment, all with the same channel names) whose saved run file and `.nd2` are both on this computer and that have the main and helper channels of the open movie's nucleus rule. **n** = their number; at least 2 are needed. Only the frame you drew on is read from each `.nd2` (read-only).
2. **Candidates** (as in section 6.13): every nucleus-sized blob on that frame is outlined exactly as AUTO-DETECT does (difference of Gaussians, outlined like a click; permissive limits 10 - 3000 µm², solidity ≥ 0.5) on the helper image, the main channel and each helper channel; a blob found again on a later image (overlap > 0.5) is not added twice.
3. **Features** of each candidate: area (µm²), circularity (4π area / perimeter²), and for the main channel and every helper its signal-to-noise (ROI mean minus the 25th percentile of a 3 µm ring, divided by the background pixel noise) and its relative brightness (signal-to-noise ÷ the 95th percentile of all candidates of the movie).
4. **Your answers**: the nucleus ROIs you saved. A candidate counts as yours when it is the best match of one of your ROIs with an overlap (intersection / union) of at least **0.3**; every saved ROI counts, so one the candidate finder never outlined counts as missed.
5. **The rule**: a minimum signal-to-noise (0, or 1 - 300 in 30 log-spaced steps) and a minimum relative brightness (0 - 1.2 in steps of 0.05) per channel, a minimum area (0 - 100 µm², 8 values), a maximum area (200 - 3000 µm², 7 values) and a minimum circularity (0 - 0.75, 7 values). Starting from "keep everything", the limits are chosen one at a time on these fixed grids (coordinate search, up to 6 rounds) to give the highest **mean F1 over the n movies**, with F1 = 2 × (your cells found) / (candidates kept + your cells), 1 = exactly your picks. A limit that makes no difference stays off; of equally good values the middle one is taken.
6. **Held-out score**: each movie is scored with the rule learned from the other n - 1 movies (leave-one-out); the sum of your cells found, of your cells and of extra cells, and the mean F1, are reported. This is the expected agreement on a movie the rule has not seen.
7. **Use**: the rule learned from all n movies selects the candidates on the open movie (nuclei only); the cells are placed as after AUTO-DETECT, for you to review. The rule is learned again, in the background, each time Smart auto-select is used.
8. **Record**: the detector's name is `<bin> - Smart auto-select (n=<n> hand-picked movies, <ROIs> ROIs)`; the run keeps the detector (rule, held-out scores, training movies), and the methods text of every export says, e.g., *Nuclei were proposed with the trained auto-detect '<name>' (PeterPiper 1.2.1, trained on <n> hand-analysed movie(s), main channel <...>). Keeps nucleus-sized blobs with ... On movies it had not seen: <a> of your <b> cells found, <c> extra (mean F1 <x>; 1 = exactly your picks).* followed by the definitions of signal-to-noise and relative brightness.

What counts as a hand-picked movie: a movie of your movie queue on which at least one ROI was added by hand since it was opened, and which you then SAVEd; its ROIs saved are the answers (all of them, also ones placed by AUTO-DETECT and kept). The number of hand-picked movies needed to unlock Smart auto-select (3) and to use a bin (2) are minimums, not recommendations: like any trained rule, it is only as consistent as the selections it learned from (section 6.13, *What to expect*; section 13).

## 9. Outputs reference

### 9.1 Folder layout

```
OUTPUT_<file name>\<user>\                  (the results folder; default next to the .nd2)
    PeterPiper_sessions\
        <file name>_session_<date>_<time>.npz      autosaved sessions
    <file name>_ROIs.npz                     SAVE (File > Save now)
    tiffs\                                   File > Export raw TIFFs...
    Graphs\                                  Save graph... (default folder)
    Comparisons\                             Compare / average runs (default folder)
        <name>.prism / .png / .jpg / .svg / .tif / .pdf / .csv / .xlsx
        <name>_per_dish.csv, <name>_pooled.csv (or _dish_means.csv)   groups only
    Export_<YYYY-MM-DD_HH-MM-SS>\            one new folder per export (1.2: or in the
                                             folder chosen under 'Save in'; with shortened
                                             names for long paths: Export_<yymmdd>-<hhmm>)
        <Compartment>\                       Nucleus, Whole cell, Cytoplasm, Mitochondria
            <name>_<comp>.xlsx
            <name>_<comp>.pzfx               (<name>_<comp>_baseline_drift.pzfx if only drift)
            <name>_<comp>_baseline_drift_T2-T9.xlsx
            Prism graphs\<comp>_<quantity>.prism
            Graphs\<quantity>.png
            CSV\<quantity>.csv
            ROI pictures\<comp>_ROIs_t<n>_<drawn|last|check>.png
        <name>_ROIs.npz
        <name>_methods.txt
        Raw TIFFs\<file name>_<channel>_t001.tif ...
        Viewing copies (PNG)\<file name>_<channel>_t001_VIEW-ONLY.png ...
```

`<name>` = the *Name for the files* (default: the first 40 characters of the `.nd2` name). **V3.0 shorter paths**: inside `OUTPUT_<movie>` the graphs, CSV tables, Prism graphs and ROI pictures no longer repeat the movie's name (the workbook, `.pzfx` and methods text keep it, so a copied file still says which movie); a *Name for the files* you type yourself is put on every file. With Windows' long paths off (Help > Computer check...), an export whose paths would be too long for Explorer (over 259 characters) or for Excel (a workbook or CSV over 218 characters) asks first; 1.2 offers shorter names, another folder or turning the setting on (section 6.7). CSV tables have Mean, SEM, n and SD columns. `<comp>` = `nucleus`, `whole_cell`, `cytoplasm` or `mito`; `<quantity>` = e.g. `R-R0 GFP-Cy5` (slashes become hyphens). Names are checked for characters Windows does not allow; nothing is ever overwritten (`_2`, `_3`, ...). Exports work even when a file's full path is longer than Windows' classic 260-character limit (deep folders, long names).

### 9.2 Excel workbook (`<name>_<comp>.xlsx`)

One workbook per compartment, all channels. **Only the Raw, Sum and Area sheets contain numbers; every other value is a live Excel formula**, so changing a 1 to 0 on the Include sheet, or the baseline dropdown on the Settings sheet, recalculates everything (open it in Excel or LibreOffice; a plain CSV reader sees the formulas, not the values). Sheet names use short channel tags (up to 7 characters).

| Sheet | Contents |
|---|---|
| Include | One row per cell: `Cell_k`, **Include (1 = yes, 0 = no)** (a dropdown; your choice in the app), **Why** (the app's reason: included / excluded by you / excluded by the IF rule / QC note). Changing it updates every mean, SEM, n and chart. |
| Graphs | Excel line charts of every F/F0 and R/R0 sheet (key quantities first): included cells dark grey, their mean blue. |
| `Raw_<ch>` | Measured ROI means (raw counts, 3 decimals). Columns: A Timepoint, B Background (the background region's mean), C... one column per cell (`Cell_k`, numbered as in the app), then `Time_min (0 = baseline)` (formula), `Mean (included)`, `SEM (included)`, `n (included)`, `SD (included)` (V3.0); row T+3 = the Include switches; hidden columns feed the charts. |
| `BgSub_<ch>` | = Raw cell - Raw background of the same row. Same columns. |
| `Noise_<ch>` (V3.0) | The noise of each ROI's mean: column B the background region's pixel SD, then per cell SD / √(ROI pixels). With *MinSNR* (Settings sheet) it decides which F/F0, ratio and R/R0 values are left out (section 8.7). |
| `dFF_<ch>` | F/F0 = BgSub / BgSub at the baseline row (`BaselineRow`). |
| `R_<a>_over_<b>` | Ratio of background-subtracted channels a / b, every ordered pair. |
| `dRR_<a>_over_<b>` | R/R0 = R / R at the baseline row. |
| `Sum_<ch>` (V2.5) | The **sum of the raw values of every pixel** of each ROI at each timepoint (counts; whole numbers written as exact integers). Column A Timepoint, B **Background sum** (the sum over the background pixels used at that timepoint), C... one column per cell as in Raw. **Raw_<ch> = Sum_<ch> / Area_px** for the same cell and timepoint (Raw is rounded to 3 decimals); Background sum / background pixels used = the Background column of Raw. |
| `Area_px` (V2.5) | Each ROI's area at each timepoint = the number of pixels of its mask in that frame (the pixels whose values were measured); column B = **background pixels used** at that timepoint (every pixel of the region; fewer only in sessions tracked with the earlier V2.5 exclusion method). |
| `Area_um2` (V2.5) | The same in µm² (pixels x pixel size²; the factor is stated in the note under the table). |
| ROI_info | Per cell: ROI type, Source, Seed area (µm², on the drawn timepoint), Mean area (µm²), Centroid X / Y (px), Timepoints re-detected (quality ≥ 0.9), Timepoints shifted (quality < 0.4), Min tracking quality, Saturated timepoints per channel, QC score, QC result. |
| QC_report | Per cell: Exported, QC passed, QC score (for ranking only), Reasons, Lost fraction, Max area jump, Signal/noise, Max saturated fraction, One-frame artefacts, Max response, Area vs median. |
| Settings | **B4 = the baseline timepoint (dropdown)**; B5 = its spreadsheet row; B6 = its time. Below: the parameter table - every value that decides a number, as actually used (Image, ROIs and tracking rules, Tracking - including the hard size limits, the rule lock and any tracker boundary lines with their coordinates -, Background - how the region was made, its area, the method (every pixel used), the fluctuation-check thresholds, the timepoints at which the background jumped with the largest jump and drift per channel, and the largest fraction of the region covered by measured cells -, Normalisation, Statistics, Quality control, Baseline drift), and "This workbook" (compartment, channels, cells exported / included, date, PeterPiper version). |
| Methods | The ready-to-edit **methods text** with references; the parameter table with what each value means; the software versions; the data file (name, full path, size, modification date, quick fingerprint, session) and the analysis date. |

Text from your input (names, reasons) is always written as literal text, never as a formula.

### 9.3 Methods text (`<name>_methods.txt` and the Methods sheet)

A plain-text methods section (UTF-8, Windows line endings) generated from the values actually used (`provenance.methods_text`): **Image analysis** (file, channels, timepoints, interval, size, pixel size, bit depth, objective), **Regions of interest** (how each compartment was outlined), **Tracking** (the rules quoted, the WITH / AND / IF sentences when used, every tracking parameter, the hard size limits - or the 0% sentence -, the no-overlap rule, the tracker boundary lines (for which cells, how many, "never crossed"), the percentage of ROI-timepoints redrawn), **Measurement**, **Background** (automatic square, clicked square or freehand outline with its area; cells included; every pixel used, the background as the sum of all the region's raw pixel values divided by their number; the fluctuation check with its thresholds, stated as informing only, and the timepoints at which the background jumped - or "No jumps were found"; sessions tracked with the earlier V2.5 exclusion method get that method's text), **Normalisation**, **Statistics**, **Quality control**, **Baseline drift**, **Software** (every version, from the running program), then numbered **References**. Words in `[square brackets]` are for you to check or fill in (e.g. "[delete if not used]" after the AUTO-DETECT mention, "[Add the number of cells and experiments and any statistical tests here.]"). If the tracking came from a version that did not record its parameters (V2.2), the text says so in brackets.

### 9.4 Prism graphs (`Prism graphs\<name>_<comp>_<quantity>.prism`, Prism 10+)

One Prism project per quantity (your chosen graph quantities, else your key quantities), made from the bundled template `app\peterpiper\templates\PeterPiper_timecourse.prism` (or your own style file).

**The built-in template look (V2.5).** Every `.prism` PeterPiper writes - single-run exports, *Save graph...*, Compare and replicate averages - starts from one built-in template: a graph the lab styled in GraphPad Prism 11, of which only the graph block with its first plot was copied into the program (none of its data, and not the path of the original file; `dev_tests/make_prism_template.py`). Its look: plain (not bold) 18 pt title and axis titles, large tick labels, a dotted line at X = 0, an open frame, filled circles of 4.32 pt in #28D2F0 with a black border, 0.59 pt lines, capped error bars (0.72 pt). `templates\PeterPiper_look.json` keeps, from the same graph, the symbol and colours of each further data set (circle, square, triangle, triangle down), used for compare / average graphs. **The graph title, axis titles, data, legend and n always come from the actual run(s).** Wherever your style equals the default (which is the template's look), the template's own bytes are kept unchanged, so Prism draws exactly the template. Three deliberate differences from the template graph:

- **error bars show SEM** (or the error you chose) - the template graph itself showed SD; the error type is a statistic, not a look;
- **the connecting line is shown** (0.59 pt), as in the live graph and the PNG - the template graph hides it; a mean line width of 0 gives exactly the template's symbols-only look in every output;
- **axes are automatic** (unless you set ranges) - the template had a fixed -5 to 55 min X axis.

A graph look carried over from an earlier version's `settings.json` takes the template values once for every setting still at the old default (mean colour, mean line width, symbol size, font size); settings the user changed are kept. A look saved inside an older session file is restored as it was (section 6.6).

Each file contains:

- **the graph, already made, in your live graph look** (V2.4): the mean of the included cells with the error you chose (SD by default; Prism computes mean and error from the replicates), X = time from baseline; graph title `<.nd2 name> - <Compartment> (n = <included cells>)`, Y axis title = the quantity, X axis title = the time label. Error type, colours, line widths, symbols and their size, each cell as a thin line, titles, axis ranges and font size are taken from the live graph. Every one of these was checked by opening the files in GraphPad Prism 11 and measuring what Prism drew;
- **tables**: the graph's own table (each included cell one replicate), `<quantity> mean, SEM, n`, `<quantity> each cell` (named columns `Cell_3`, `Cell_7`, ...) and, if chosen, the baseline drift slopes (a column table, one row per cell);
- project notes: what the numbers are and how the baseline was set.

**Looks Prism cannot draw** get the closest Prism look, and the live graph shows a small brown note saying what the Prism file shows instead (nothing is shown when Prism matches):

| Your look | In the `.prism` file |
|---|---|
| Shaded error band | error bars of the same type (SEM / SD / 95% CI) |
| Mean hidden (*each cell only*) | the mean as a 0.12 pt hairline without symbols or error bars |
| Mean line width 0 | V2.5: symbols not joined (the template's own look); without symbols as well, a 0.12 pt line (otherwise nothing would be drawn) |
| Cell line width 0 | 0.12 pt (Prism draws lines in steps of 0.12 pt) |
| Symbol size 0 | no symbol (the same look) |
| Dashed line at time 0 | left out (add one in Prism if needed) |
| Key (legend) | left out |
| Picture width / height | PNG / SVG only; the Prism graph keeps its own size |

**Your own template** (*Choose style...*): a file made from a PeterPiper `.prism` gets your live look as above; any other Prism graph keeps its own look and gets only the data and texts (section 6.7). The methods text says what the Prism graphs show (e.g. "mean ± SD (error bars)").

Only Prism 10 or newer opens `.prism` files (verified with Prism 11). Fixed in V2.3: the template's error bars now show SEM (V2.2 drew SD while the label said SEM; section 15).

Compare / average runs (section 6.10) writes its own `.prism` into `<results folder>\Comparisons\`, in the same template look: one data set per line (replicates = cells, or for *Groups - mean of dish means* one column per dish holding that dish's mean, so Prism's error bars are SEM across dishes), a legend in table order, one colour per line (by cell line) and the template's symbol per data set, a *mean, SEM, n* table per line and, for groups, an *each dish mean* table and the statistic not plotted.

**A graph for every table (V2.7).** Every XY table in a `.prism` PeterPiper writes - *mean, SEM, n*, *each cell*, the per-dish means of a group, the right-axis measure - gets its **own graph**, made from the same template (your graph style, section 6.11) with that table's data and title; tables with more than 12 data sets (each cell) are drawn as thin grey lines without a legend. Column tables (kinetics, drift per cell) get a graph from your column graph style once you have made it. How: each extra graph is a copy of the template's graph block given what GraphPad Prism 11's own *Duplicate family* gives a copy - new ids for every graph object, plot and axis segment (unique in the document), its own fenID, the fenID of the data table it belongs to, its data sets - worked out by letting Prism duplicate a PeterPiper graph and comparing the two, and checked by opening the files in Prism 11 (each graph shows only its own table's data, with its own titles). Automatic axes also get an automatic tick interval (the template's Y interval was set by hand for ratios and drew a label at every unit of an intensity axis).

### 9.5 Prism tables (`<name>_<comp>.pzfx`, any Prism version)

Per quantity, three XY tables with X = time from baseline: `<quantity> - cells as replicates` (one data set, each included cell a replicate - graph it in Prism as mean ± SEM or each replicate), `<quantity> - mean, SEM, n`, `<quantity> - each cell`; with drift, one column table of slopes per quantity (graph as scatter dot plot). The project notes record the PeterPiper version and date, the tracking rules, the baseline timepoint and a short fingerprint. With a Prism `.pzfx` template chosen, `..._with_graphs.pzfx` adds your template's graphs filled with these tables.

### 9.6 CSV tables (`CSV\<name>_<quantity>.csv`)

One per quantity (every background-subtracted intensity, F/F0, ratio and R/R0): columns *time from baseline*, Timepoint, `Cell_k` for each included cell, Mean, SEM, n; values with 6 significant digits; empty = no value.

### 9.7 Graphs (`Graphs\<name>_<quantity>.png`)

300 dpi PNG (1800 x 1350 pixels with the default 6 x 4.5 inch size) of the included cells, in your graph look (the same as the *As exported* view); title by default `<name> - <Compartment> (n = <n>)`.

### 9.8 Baseline drift (`<name>_<comp>_baseline_drift_T<a>-T<b>.xlsx`)

Sheet "Baseline drift": per cell, Include (1/0) and the slope per quantity (per minute); then Mean, SEM and n of the included cells. The Prism files get one dot-plot table per quantity.

### 9.9 ROI pictures (`ROI pictures\...png`)

Full resolution (one image pixel per pixel) of the compartment's rule channel A at that timepoint (display range 1st - 99.7th percentile), every ROI outlined: included cells in their colour (the same as in the app) with the cell number, excluded cells grey dashed, the background region green. Choices: the drawn timepoint, the last timepoint, every 10th timepoint.

### 9.10 Raw TIFFs and viewing copies

- **Raw TIFFs**: one 16-bit TIFF per channel and timepoint, `<file name>_<channel>_t###.tif`, **pixel values unchanged** (raw counts), ImageJ-format with the pixel size and a display range (0.5 - 99.7th percentile of the first timepoint) so Fiji / ImageJ open them visible. (Windows Photos shows raw 16-bit images almost black - that is the viewer, not the data.)
- **Viewing copies**: 8-bit PNG, contrast-stretched with the same range for every timepoint of a channel, named `..._VIEW-ONLY.png`. For looking only - never measure them.

### 9.11 ROI files and session files (`.npz`)

A NumPy `.npz` archive (a zip of arrays; `np.load(path, allow_pickle=False)`). Masks are bit-packed (`np.packbits`; unpack with `np.unpackbits(m)[:h*w].reshape(h, w)`).

| Array(s) | Contents |
|---|---|
| `n`, `bbox_i`, `shape_i`, `mask_i`, `flags_i` | One anchor ROI per cell (box `y0, x0, y1, x1`, mask, include / hand-drawn flags) - readable by every PeterPiper version. |
| `comp_<c>_n`, `comp_<c>_bbox_i`, `comp_<c>_shape_i`, `comp_<c>_mask_i`, `comp_<c>_outline_i` | Every ROI of compartment `c` (`nucleus`, `cell`, `cytoplasm`, `mito`) as drawn, per cell (`outline` = the followed region for cytoplasm / mitochondria). |
| `bg_bbox`, `bg_shape`, `bg_mask` | The background region. |
| `image_shape`, `seg_timepoint` | Image height and width; the drawn timepoint (1-based). |
| `state_json` | JSON: `version`, `saved`, `kind` (`session` / `export` / `saved`; `saved` = SAVE or *Save ROIs now*), `note` (1.1: the note typed with SAVE), `session_id`, `nd2` (name), `nd2_path`, `fingerprint`, `exp` (pixel size, interval, timepoints, width, height, channels, bit depth), `channels`, `t0`, `cells` (per cell: compartment → channel drawn on), `excl` (excluded cells per compartment), `rules`, `follow`, `bg_auto`, `bg_kind` (V2.5: `auto` / `click` / `hand`), `boundaries` (V2.5: `{cell index (0-based, text): [[[x, y], ...], ...]}`), `prefix`, `baseline`, `drift`, `track_params`, `graph_style`, `based_on` (the earlier run loaded, if any), `content_key` (V2.5, section 7). |
| `track_json` | JSON: tracked compartments, redrawn fractions, `rules`, `params` (every tracking parameter), `gate` (IF signal-to-noise per cell), `background` (V2.5: the region's size, the fraction covered by measured ROIs per timepoint and the fluctuation check per channel), channel names per compartment. |
| `trk_<c>_bbox` (T, N, 4), `trk_<c>_shape` (T, N, 2), `trk_<c>_off` (T, N, 2), `trk_<c>_hasout` (T, N), `trk_<c>_bits` | The tracked ROI of every cell at every timepoint (masks and outlines bit-packed one after another; `off` = their offsets). |
| `trk_<c>_m_mean` (T, C, N), `_background` (T, C), `_background_sd` (T, C), `_area_px` (T, N), `_n_saturated` (T, C, N), `_quality` (T, N); V2.5: `_sum` (T, C, N), `_background_sum` (T, C), `_background_npx` (T) | All measurements. |
| `trk_bgx_t`, `trk_bgx_shape`, `trk_bgx_bits` (V2.5) | Only in sessions tracked with the earlier V2.5 exclusion method: the background pixels left out as bright / moving objects or ROIs, per timepoint that had any (bit-packed masks in the background region's box). Not written now - nothing is left out. |

Session files have the same content (`kind = "session"`), written with faster compression. V2.2 reads the ROIs and tracking of V2.3 and V2.4 files. Files without the V2.5 fields load as before.

### 9.13 Saved files log (`saved_files_log.jsonl`, V2.8)

Every save - an export, *Save graph...*, a Compare / average save, a batch analysis - adds one line to `saved_files_log.jsonl` next to `settings.json`: when, what, the name you gave it, the folder and every file written (`peterpiper/outlog.py`). **Saved files...** (start window, *File* menu, Compare window) lists them newest first with a filter box; click a save to see its files, double-click to open the folder or a file. Files moved or deleted since are marked. The log holds paths only; deleting it never touches your files.

### 9.12 Settings and run index

`settings.json` holds the last-used settings (all fields of `config.Settings`). `compare_colours.json` (V2.5, same folder) holds `{"names": {name in lower case: "#RRGGBB"}}` - the colours chosen in the *Compare / average runs* window for unknown cell lines, groups and runs. `compare_window.json` (V2.5, same folder) holds `{"cell_lines": {run key: cell line}, "table": {"order", "sort", "widths"}}` - the cell line chosen in that window per `.nd2` (run key = its content fingerprint, else the run file's normalised path; `Unknown` = no cell line on purpose) and the list's column order, sort and widths (by column title); V2.6 adds `"groups": {"path:<run file>" or "fp:<.nd2 fingerprint>": group}`, `"labels": {"path:<run file>": name in the graph}` (only names you changed), `"view": {"ticked", "mode", "comp", "quantity", "graph", "kinetics"}` and `"sort_v25b"` (the list was switched once to the newest-first *Version* sort). 1.1 adds small per-user files in the same folder, each one JSON object written in one step (`peterpiper/userprefs.py`): `storage.json` (`results_root`, `backup_root`), `queue.json` (`items`: `nd2`, `status`), `smartselect.json` (`bins`: name → channels, created; `movies`: `nd2`, `run`, `n_hand`, `n_cells`, `channels`, `bin`, `reviewed`, `saved`), `charlotte.json` (the game's collection), `achievements.json` (hidden extras found, with dates), `sync.json` (the keep-in-step folder and per-file checksums) and, only with a password, `password.json` (`algo` = `pbkdf2_sha256`, `n` = 200000, `salt`, `hash`, `set`). `run_history.json` maps each `.nd2` fingerprint to its name, size, last 10 paths and up to 100 runs (ROI / session file paths with their summary); at most 2000 `.nd2` files are remembered; runs whose file no longer exists are pruned; a damaged index is set aside as `run_history.corrupt.json` and a new one started. An index that exists but cannot be read at that moment (locked by another program, no permission) is never replaced. Two PeterPiper windows or programs recording runs at the same time take turns (a short-lived `run_history.lock`), and each re-reads the index just before writing, so neither loses the other's runs.

## 10. Reproducibility

What is recorded, and where:

| Recorded | Where |
|---|---|
| PeterPiper version (`1.2.1`), Python version, operating system, and the version of every library that touches the numbers | Methods sheet, methods text (Software paragraph); ROI / session files (`version`) |
| Exact installed package versions | `%USERPROFILE%\.PeterPiperV1.2\venv\installed_versions.txt` (or the reused install's, e.g. `.PeterPiperV1.1\venv\installed_versions.txt`, section 3.2) |
| The `.nd2` file: name, full path, size, modification date, **quick fingerprint** (SHA-1 of the file size + the first and last 4 MiB; the whole file if ≤ 8 MiB) | Methods sheet, ROI / session files, Prism notes (short form) |
| Pixel size, frame interval, timepoints, image size, channels, bit depth, objective | Settings and Methods sheets, methods text, ROI files |
| Tracking rules (with channel names) and every tracking parameter, including the frozen WITH / AND / IF normalisation | Settings and Methods sheets, methods text, ROI files (`rules`, `track_params`, `track_json`) |
| ROIs as drawn, every tracked ROI at every timepoint, all raw measurements (V2.5: also the raw sums and the background pixel counts) | ROI / session files; Raw, Sum_, Area_px, Area_um2 sheets |
| Tracker boundary lines (per cell, image coordinates) | Settings and Methods sheets, methods text, ROI files |
| Include / exclude choices and the reason for each cell | Include sheet, ROI files |
| Background region (automatic, clicked square or freehand), its area, the method (every pixel used), the fluctuation check and the timepoints at which the background jumped | ROI files; Settings and Methods sheets, methods text; Area_px sheet (pixels used) |
| Replicate averages: which dishes in which group, each dish's mean and n, the alignment | Compare / average outputs (per-dish table, Methods sheet of the `.xlsx`, `.prism` notes) |
| Baseline, drift window, graph look | Settings sheet, ROI files |
| A trained auto-detect or Smart auto-select used for the nuclei: its name (for Smart auto-select: bin, n hand-picked movies, ROIs), rule and held-out score | ROI / session files (the detector), Methods sheet and methods text |
| Which saved version a run is: SAVE / autosave / export, and the note typed with SAVE (1.1) | ROI / session files (`kind`, `note`); Compare's *Save* column |

To reproduce or audit an analysis:

1. Keep the exported ROI file with the results (it is on the Standard set). Loading it with the same `.nd2` restores the exact ROIs, tracking and choices; exporting again gives the same numbers.
2. To re-track from the same ROIs, load the ROI file, change nothing and press TRACK & MEASURE. PeterPiper uses no random numbers; with the same file, ROIs, rules, boundary lines, settings and package versions the tracking is the same (in the V2.3 tests, separate tracking runs on the same input agreed array by array). Re-tracking an analysis made before V2.5 uses the V2.5 tracker and background, so its numbers can differ from the original ones (section 7).
3. Use the pinned install (Python 3.11 - 3.14) for published work and keep `installed_versions.txt`.
4. Archive the `.nd2`; the fingerprint shows whether a file is the one analysed (a change in the middle of a file larger than 8 MiB is not detected by the quick fingerprint).

## 11. Using PeterPiper in a paper

### 11.1 Start from the generated methods text

Every export can include `<name>_methods.txt` (and every workbook has the same text on its Methods sheet), with the values actually used for that analysis and the references. Edit it: remove "[delete if not used]" parts that do not apply, fill in the bracketed items, and shorten as your journal requires.

### 11.2 Template paragraph

Adapt this; replace every `[...]`. Values shown are PeterPiperV1.2 defaults - use the values from your Methods sheet.

> **Image analysis.** Time-lapse images were analysed with PeterPiper [1.2.1] [ref PeterPiper] directly from the Nikon NIS-Elements .nd2 files (read with the nd2 package [ref]), using the raw pixel values [and maximum-intensity projections of the Z stacks]. [Nuclei / Whole cells / Cytoplasm / Mitochondria] were outlined on [channel] on timepoint [1] by clicking on each cell, the outline being computed from the image around the click [nuclei: the connected region above the local background plus 35% of the difference to the nuclear interior] [and reviewed or corrected by hand]; [cells were proposed automatically and reviewed] [or, with Smart auto-select: nuclei were proposed by a user-specific detector learned from [n] movies of the same experiment type in which cells had been selected by hand ([N] ROIs; held-out mean F1 [x], each movie scored by the rule learned from the others) and reviewed by hand]. [Tracking rule(s), e.g. "Whole cells were followed on mRuby; within each outline, only pixels where mRuby and GFP, each scaled between its background and bright level measured on the drawn timepoint, were jointly above the outline's edge level were measured" / "only cells with a GFP signal-to-noise ratio of at least 5 on the drawn timepoint were analysed".] Each cell was followed through all timepoints: its displacement between consecutive timepoints was measured by sub-pixel phase cross-correlation [ref scikit-image; ref Guizar-Sicairos] (upsampling factor 10, at most [3] µm), and every ROI was redrawn at every timepoint from that timepoint's pixels at the ROI's own relative edge level, with neighbouring cells kept apart (no pixel shared between cells) [and user-drawn boundary lines between touching cells never crossed], and the ROI area constrained to 0.67-1.5 times the previous timepoint's area and strictly to within ±[25]% of the drawn pixel count (larger outlines trimmed to their brightest connected pixels, smaller ones grown by their brightest neighbouring pixels) [or: and the ROI given exactly the drawn pixel count at every timepoint]; where no acceptable outline was found ([x]% of ROI-timepoints), the previous outline was moved with the cell. At every timepoint the mean intensity of every channel was measured in every ROI from the raw pixels (sum of the pixel values divided by the number of pixels). The background was measured at every timepoint in [a 150 µm square region placed automatically away from the measured cells / a region drawn by hand], which could contain non-transfected cells so that their autofluorescence was included in the background; at every timepoint the mean of all the region's pixels (the sum of the raw values divided by their number) was subtracted from every ROI of the same channel and timepoint. The background trace of each channel was checked for jumps (more than 5 robust SD of the jumps and more than 5% of the background level away from its running median over 5 timepoints) and for drift (running median changing by more than 20%); this check did not change any value [and no jumps were found / and the region was redrawn where it flagged a passing bright cell]. Ratios ([A/B]) of background-subtracted intensities were calculated, and intensities (F) and ratios (R) were normalised to timepoint [1] (F/F0, R/R0; time 0). Cells were included after visual inspection of the tracked outlines [and the automated quality-control notes]. For each dish, the mean of its included cells was calculated at every timepoint; data are shown as the mean ± SEM of the dish means (n = [N] dishes, SD with n - 1, SEM = SD/√n; [n] cells in total), using only frame times common to all dishes, without interpolation [state tests]. Analyses used Python [3.11.9] [ref] with NumPy [2.4.6] [ref], SciPy [1.17.1] [ref], scikit-image [0.26.0] [ref], nd2 [0.12.0] [ref], matplotlib [3.11.2] [ref], pyqtgraph [0.14.0] [ref], PySide6 [6.12.0] [ref] and openpyxl [3.1.5] [ref]; graphs were made in GraphPad Prism [version] [ref].

### 11.3 What to report

- PeterPiper version; Python and package versions (Methods sheet, or `installed_versions.txt`).
- Pixel size, frame interval, number of timepoints; Z projection if any; which stage position.
- For each compartment: the tracking rule, channel(s) used for outlining, and whether ROIs were clicked, auto-detected and reviewed, or drawn by hand, and whether outlines were corrected by hand (resized, split, merged, extended).
- If Smart auto-select (or a trained auto-detect) proposed the cells: the bin (kind of experiment), **n** = the number of hand-picked movies it learned from and the number of ROIs in them, its **held-out F1** (each movie scored by the rule learned from the others; in the methods text), and that the proposals were reviewed - all written in the methods text of each run (section 8.13). The same person should have hand-picked the training movies and the analysed ones, or say who did.
- The size guard (`size_tol`, default ±25%, a hard limit since V2.5; 0% = exactly the drawn pixel count), the largest movement (`max_move_um`, 3 µm), and - if used - `gate_snr` (IF, 5), `overlap_k` (AND, 3) and `mito_k` (mitochondria, 3).
- Whether tracker boundary lines were drawn, and for how many cells.
- The fraction of ROI-timepoints redrawn (reported after tracking and in the methods text).
- Background: one region per movie (automatic 150 µm square, clicked 60 µm square or drawn by hand), cells included, every pixel used at every timepoint; the fluctuation check and the timepoints at which the background jumped, and whether the region was redrawn (Settings sheet / methods text).
- Baseline timepoint; normalisation (F/F0, R/R0); which ratio.
- Inclusion criteria: how cells were included / excluded (inspection, QC notes, IF gate, AUTO-DETECT brightness slider), and how many cells were excluded and why.
- Number of cells and of independent dishes / experiments; **the experimental unit** (n = dishes: mean of dish means; pooled cells are not independent replicates); how time points were aligned; error type (SEM, SD or 95% CI); statistical tests.

### 11.4 References

Software used by PeterPiper (cite those relevant to your analysis):

1. **NumPy** - Harris, C.R., Millman, K.J., van der Walt, S.J. et al. Array programming with NumPy. *Nature* 585, 357-362 (2020). https://doi.org/10.1038/s41586-020-2649-2
2. **SciPy** - Virtanen, P., Gommers, R., Oliphant, T.E. et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods* 17, 261-272 (2020). https://doi.org/10.1038/s41592-019-0686-2
3. **scikit-image** - van der Walt, S., Schönberger, J.L., Nunez-Iglesias, J. et al. scikit-image: image processing in Python. *PeerJ* 2, e453 (2014). https://doi.org/10.7717/peerj.453
4. **nd2** - Lambert, T. nd2: a Python reader for Nikon NIS-Elements .nd2 files. https://github.com/tlambert03/nd2
5. **matplotlib** - Hunter, J.D. Matplotlib: a 2D graphics environment. *Computing in Science & Engineering* 9(3), 90-95 (2007). https://doi.org/10.1109/MCSE.2007.55
6. **pyqtgraph** - Campagnola, L. et al. PyQtGraph: scientific graphics and GUI library for Python. https://www.pyqtgraph.org
7. **Qt / PySide6** - The Qt Company. Qt for Python (PySide6). https://doc.qt.io/qtforpython-6/
8. **openpyxl** - Gazoni, E. & Clark, C. openpyxl: a Python library to read/write Excel 2010 xlsx/xlsm files. https://openpyxl.readthedocs.io
9. **tifffile** - Gohlke, C. tifffile: read and write TIFF files. https://github.com/cgohlke/tifffile
10. **imagecodecs** - Gohlke, C. imagecodecs: image transformation, compression, and decompression codecs. https://github.com/cgohlke/imagecodecs
11. **dask** - Rocklin, M. Dask: parallel computation with blocked algorithms and task scheduling. In *Proceedings of the 14th Python in Science Conference* (SciPy 2015), 130-136. https://doi.org/10.25080/Majora-7b98e3ed-013 ; Dask Development Team. Dask: library for dynamic task scheduling (2016). https://dask.org
12. **GraphPad Prism** - GraphPad Prism version [x] for Windows, GraphPad Software, Boston, Massachusetts, USA. https://www.graphpad.com
13. **Python** - Van Rossum, G. & Drake, F.L. *Python 3 Reference Manual*. CreateSpace, Scotts Valley, CA (2009); Python Software Foundation, https://www.python.org

Methods implemented by these libraries and used by PeterPiper:

14. **Sub-pixel registration (phase cross-correlation)** - Guizar-Sicairos, M., Thurman, S.T. & Fienup, J.R. Efficient subpixel image registration algorithms. *Optics Letters* 33(2), 156-158 (2008). https://doi.org/10.1364/OL.33.000156
15. **Otsu threshold** - Otsu, N. A threshold selection method from gray-level histograms. *IEEE Transactions on Systems, Man, and Cybernetics* 9(1), 62-66 (1979). https://doi.org/10.1109/TSMC.1979.4310076

The generated methods text cites references 1-9, 11-13 in the order they first appear (it uses the Python Software Foundation and Dask Development Team forms).

Colour and accessibility checks of the user interface (1.1, section 6.18; they do not concern any measurement):

16. **Colour-blind-safe hues** - Okabe, M. & Ito, K. Color Universal Design (CUD): how to make figures and presentations that are friendly to colorblind people (2008). https://jfly.uni-koeln.de/color/
17. **Colour-vision-deficiency simulation** - Machado, G.M., Oliveira, M.M. & Fernandes, L.A.F. A physiologically-based model for simulation of color vision deficiency. *IEEE Transactions on Visualization and Computer Graphics* 15(6), 1291-1298 (2009). https://doi.org/10.1109/TVCG.2009.113
18. **CIEDE2000 colour difference** - Sharma, G., Wu, W. & Dalal, E.N. The CIEDE2000 color-difference formula: implementation notes, supplementary test data, and mathematical observations. *Color Research & Application* 30(1), 21-30 (2005). https://doi.org/10.1002/col.20070
19. **WCAG 2 contrast** - World Wide Web Consortium (W3C). Web Content Accessibility Guidelines (WCAG) 2.1 (2018). https://www.w3.org/TR/WCAG21/

### 11.5 How to cite PeterPiper

> DePaola P IV. PeterPiper: single-cell fluorescence time-course analysis for Nikon .nd2 movies, version 1.2.1 (2026). Schmitt Lab, University of California, Los Angeles. https://github.com/peterdepaola4/PeterPiper https://doi.org/10.5281/zenodo.24120837.

`CITATION.cff` in the repository holds the same (GitHub shows it as *Cite this repository*). Name the version you used (`1.2.1`; the program `PeterPiperV1.2`, shown in the window title, the Settings sheet and every methods text) and keep the exported methods text and provenance with your data.

## 12. Validation

**V2.8.** Every developer test was run again on the final V2.8 code (3 November 2026), all passing: the new `test_v28.py` 54/54; `test_v27.py` 35/35 and `test_v27_batch.py` 17/17; kinetics 55/55; Compare runs 43/43; replicate averaging and the compare window 77/77; the V2.5 tracking features 51/51 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; session memory 57/57; trace panel and graph look 61/61; graph statistics 144/144 and on real measurements 8/8; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher 14/14. `test_v28.py` checks every new measure against hand-computed numbers (raw intensity = the ROI mean, background = one value per dish, ΔF/F0 and ΔR/R0 = F/F0 − 1 and R/R0 − 1, sum intensity = (mean − background) × area, area in µm² = px × pixel size², nucleus / cytoplasm ratio per cell over the cells included in both, and ÷ baseline), that every V2.4 quantity is unchanged, the plain warnings (X = Y, background asked per cell), background never paired per cell; the run list in folders by group with movie sub-folders (newest first), one analysis per movie in the Groups modes (and two side by side in Each run, with the red note), group folder ticks, new / rename / delete / take out, a movie's analyses moving together; the graph toggles (Y error bars by default, X off, each cell), a legend click hiding a line with its own error bars only, the hover readout, mean ± SD by default, the Timepoint axis, a right axis against a measure, the red warning, explanations on every dropdown entry, trajectory start / end markers and the dot-plot mean cross, resizing (dividers that cannot collapse a part, scrolling settings, a minimum size), the saved-files log and its window, saving Y vs X with a right axis and an N/C ratio time course of groups; and the `.prism` files opened in GraphPad Prism 11. A stress test on the lab's 34 real runs (not shipped: `_work/stress28.py`) drew 1,125 plots - every measure × every X choice × every Show mode × both kinds of points, the toggles switched 90 times, right axes, kinetics graphs - with no error and no plot slower than 3 s, saved every file type (a time course with kinetics: 48 files in 8 s), and handled nothing ticked, a single dish and removing one analysis of a movie. Tests changed on purpose: the Compare tests now use the run tree (by run, not by row), expect the V2.8 Version wording ('newest of 3') sort before grouping (the list is sorted inside each group folder), accept the cell-line shades in either list order, and answer the new Save options dialog.

**V2.7.** Every developer test was run again on the final V2.7 code (2 November 2026), all passing: the new `test_v27.py` 35/35 and `test_v27_batch.py` 17/17; kinetics 55/55; Compare runs 43/43; replicate averaging and the compare window 77/77; the V2.5 tracking features 51/51 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; session memory 57/57; trace panel and graph look 61/61; graph statistics 144/144 and on real measurements 8/8; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher 14/14. `test_v27.py` checks the plot builder against hand-computed numbers: measures in words, paired cells (only cells included in both compartments), Y = the export's F/F0 and X = the background-subtracted intensity of the same cells, trajectory means and SEM (SD n - 1 / sqrt n), time from the baseline, each cell at a timepoint and over a window, groups (dish means as replicates, pooled cells); in the window: the dropdowns offer what the runs have, 'over' only for ratios, the right Y axis, the sentence, the remembered plot, every saved file (never overwritten); and the `.prism` files opened in GraphPad Prism 11. `test_v27_batch.py`: saved settings round trip; a batch analysis of a real U2OS movie (read only) with saved settings - 50 nuclei found, tracked and exported (workbook, ROI file, methods) with no dialog waiting, the user's `settings.json` unchanged, the log written; the Prism style templates made, used and reset. The background object check: a whole-region 8% flicker at one timepoint, 40% bleaching and 1.5% cell overlap give no warning; a bright cell floating in at one timepoint and 15% cell overlap do (`test_v25_track.py`). The per-table Prism graphs were checked by opening the files in Prism 11 and looking at every graph (each shows only its own table, its own titles, a readable axis); the column graph from a column template was checked with a Prism example graph standing in for yours. One test was changed on purpose: `test_prism_live.py` allows 0.12 pt rounding at both ends of every drawn error-bar segment (Prism now draws each bar as one segment because the tick interval is automatic). Not tested: a column graph template made by you in Prism (the mechanics were tested with Prism's own column example), and the batch dialog clicked on screen (its steps run offscreen).

**V2.6.** Every developer test was run again on the final V2.6 code (2 November 2026), all passing: the new `test_v26_kinetics.py` 55/55; Compare runs 43/43; replicate averaging, cell lines and the compare window 77/77; the V2.5 tracking features 47/47 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; trace panel and graph look 61/61; session memory and earlier-runs dialog 57/57; graph statistics 144/144 and on real measurements 8/8; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher messages 14/14. `test_v26_kinetics.py` (not shipped) checks: every kinetics number on a hand-made curve worked out by hand (baseline, peak, amplitude, interpolated t10 / t½ / t90, 10-90% rise time, least-squares initial slope, maximum rate), t½ of an exact exponential rise, a fall, the flags; per-group mean / SD / SEM / 95% CI over dishes against NumPy / SciPy; the kinetics PNG / SVG / `.prism` files and the CSV / Excel numbers; nothing overwritten; the window's kinetics dot plot and Save; groups, graph names, ticked runs and view remembered in a new window (and a new analysis of a grouped dish joining its group); the value at the baseline timepoint used as the baseline (not drifting earlier frames), the window end, the same window for dishes of different lengths (identical curves give identical t½; with their own windows the longer movie gets a later t½), one row for an export and its identical session, the column order moved once, visible tick boxes; the versions of one `.nd2` (own colour per set, newest / older / oldest by saved date, newest-first sort with older analyses under the newest); and the kinetics `.prism` opened in GraphPad Prism 11 ("COMPLETE! No Errors.", legend with n dishes, error bars = SEM across the dishes, group colours drawn).

**V2.5.** Every developer test was run again on the final V2.5 code (2 November 2026), all passing: tracking-rule unit tests 37/37 and real-data tracking 33/33; the V2.5 rule lock, size 0%, boundaries, background and de-duplication 42/42 on the synthetic movie, and passing with `--real` (the real U2OS movie); the V2.5 main-window features 25/25 (with the real movie); ROI / session files and run index 59/59; provenance 47/47; graph statistics and drawing 144/144 and on real measurements 8/8; Compare runs 43/43; replicate averaging, cell-line colours, the compare window's cell-line dropdown, sorting, movable columns and same-`.nd2` warning, and their Prism files 77/77; Prism look written into `.prism` files 52/52 and the Prism style field matrix with 0 failures; GUI tests (offscreen) - tracking rules 84/84, session memory and earlier-runs dialog 57/57, trace panel and graph look 61/61, the V2.2 click-workflow regression 31/31; launcher messages 14/14; zip build 14/14. Prism files were opened and measured in GraphPad Prism 11.

New V2.5 developer tests (not shipped in the zip): `test_v25_track.py` - the rule lock (WITH / AND / IF ROIs are subsets of the ONLY ROI of the same cell at every timepoint and within the hard size cap, on a synthetic movie and on a real U2OS nucleus movie), size 0% (every timepoint has exactly the drawn pixel count), boundary lines (no ROI pixel ever on or beyond a line), the background (nothing left out: background sum = the sum of every region pixel and pixel count = the whole region at every timepoint; a dead / very bright object and a passing object reported as background jumps at their timepoints; the note names them and says every pixel was used; a steady background gives no note; ROI mean = sum / area), no two cells' ROIs overlapping in a timepoint, the content key and the de-duplication, the Sum_ / Area_px / Area_um2 sheets (Raw = Sum / Area_px), and older files without the V2.5 fields; `test_compare_groups.py` - cell-line recognition (look-alike characters, no false positives such as "anchor"), the shades, the group statistics on hand-made numbers (dish mean over included cells, mean / SD (n - 1) / SEM / 95% CI over dish means, pooled cells), alignment (30 s vs 60 s intervals, different lengths, a dish without cells), every saved format with the numbers checked against the hand-made ones, the window offscreen (the Cell line dropdown - chosen line wins, a new name's colour asked once, remembered per `.nd2` across windows, used by *Group by cell line*; sorting numbers, natural names and dates with every row keeping its run; movable columns with order, widths and sort remembered; the same `.nd2` found by fingerprint, path or name and size, never across different fingerprints, the orange mark, the red warning and *Save...* asking first), and the group, run-compare and single-run `.prism` files opened in GraphPad Prism 11 (error bars = SEM across dish means, legend with n dishes / cells, the template look); `test_gui_v25.py` - the main-window features offscreen (0% size, AUTO-DETECT slider and its Undo, freehand and clicked background, tracker boundary drawn, saved, reloaded and obeyed, a session not saved again when unchanged). The V2.4 tests below were updated where V2.5 intentionally changed a result (tracking rules, Prism look, provenance).

**V2.4.** Every developer test below was run again on the final V2.4 code (31 October 2026), all passing: tracking-rule unit tests 37/37 and real-data tracking 33/33; ROI / session files and run index 59/59; provenance 47/47; graph statistics and drawing 144/144 and on real measurements 8/8; Compare runs 43/43; Prism look written into `.prism` files 52/52 and the Prism style field matrix 45/45 (0 failures); GUI tests (offscreen) - tracking rules and the new step-3 settings 84/84, session memory and earlier-runs dialog 57/57, trace panel and graph look 61/61, the V2.2 click-workflow regression 31/31 (also run on the built release); launcher messages 14/14; zip build 14/14; and the package pins resolve to ready-made wheels for 64-bit Windows with Python 3.11 - 3.14 (3.10: compatible list). New V2.4 checks include: each tracking setting clears the tracking and is saved with the session; the IF / AND settings appear only with their rule; an index that cannot be read is left untouched and two writers at once lose no run; the newest run is preselected; an AND frame with no kept pixels shows the followed outline; closing during tracking closes the `.nd2` only after the job has stopped; untracked stray files never reach the zip. The Prism look, *Load look from a Prism file* and the Compare runs `.prism` were checked by opening the files in GraphPad Prism 11 and measuring the drawings.

The following automated checks were run for V2.3 (developer tests, not shipped in the zip; real data = the lab's own `.nd2` movies of U2OS nuclei, HeLa whole cells and MEF / MCF10A mitochondria, read-only):

- **ONLY rules are bit-identical to V2.2.** The V2.3 tracker without rules and with ONLY rules was compared with the V2.2 tracker on real data (nuclei on Cy5, whole cells on mCherry, mitochondria on GFP; drawn timepoint 1 and 6, which exercises the backward pass): every measurement array and every per-timepoint box, mask, outline, channel and include flag is exactly equal.
- **WITH, AND, IF on real data.** WITH (mCherry with GFP, whole cells): every outline stayed within the size guard (area / drawn 0.89 - 1.29), all measurements finite, and the drawn timepoint is redrawn on exactly the image it was drawn on. AND (mitochondria GFP and ExRai): every AND mask is a subset of the ONLY mask with an identical outline; a sweep of k = 3 / 10 / 30 / 100 / 300 kept 100 / 86 / 43 / 8 / 0% of the pixels; on nuclei (Cy5 AND GFP) 17 - 100% were kept and an ROI in an empty area measured NaN with quality 0.3. IF: gate signal-to-noise values from 1.0 (an ROI on background, correctly excluded with its reason) to 1901; outlines and measurements identical to ONLY. Speed: ONLY / V2.2 = 0.96; WITH about +32%. (Unit tests 37/37, real-data tests 33/33.)
- **ROI and session file round trips.** The user's real V2.2 tracked file (61 timepoints, 10 cells) loads with its tracking; re-saving it gives bit-identical arrays; session files are replaced atomically (a simulated crash during writing leaves the old file intact) and never replace a non-session file; the unchanged V2.2 code reads V2.3 session files with identical ROIs and tracking; V1.6, V2.0 / V2.1 and damaged files are handled. Fingerprints, the earlier-runs search (synthetic tree and real folders) and the run index were tested. (57/57 checks.)
- **Exports identical to V2.2 where nothing should change.** Every workbook sheet except the new Settings rows and the Methods sheet matches the V2.2 workbook cell by cell (value, formula, type), including all 255 formula references to the Settings sheet; the only intended difference is that text starting with `=` is now literal text. `.pzfx` tables are identical to V2.2; all 18 CSV files of a real analysis are byte-identical to V2.2. Mean, SD, SEM, 95% CI and n match independent NumPy / SciPy calculations; the panel's saved PNG is byte-identical to the exported PNG. (47/47 and 140/140 + 8/8 checks.)
- **Prism SEM fix verified in Prism 11.** The bundled template's error bars were changed from SD to SEM (one byte in the graph's plot record) and the before / after files were rendered by GraphPad Prism 11 itself.
- **GUI tests** (offscreen): tracking rules in the window 67/67, a V2.2 regression of the whole click workflow (auto-detect, click add, resize, split, add to cell, undo, track, save, reload with tracking, export) 31/31, session memory 53/53.
- **Real install test.** The `.bat` was run non-interactively on a clean folder: fresh install in 250 s with the exact list; the installed `pip freeze` equals `requirements.txt` for all 45 packages; the second start took 0.1 s; a deliberately impossible pin falls back to the compatible list and says so; a too-long install path, a missing Python, an old Python and an unextracted zip give their messages. (22/22 checks.) The pinned versions resolve to ready-made wheels for 64-bit Windows with Python 3.11, 3.12, 3.13 and 3.14; Python 3.10 resolves with the compatible list. The zip build is reproducible (13/13).

Not covered by automated tests: Excel and LibreOffice were not used to recalculate the workbooks (formulas were checked structurally); `.pzfx` files were not opened in Prism (their tables are identical to V2.2's); Prism 10 was not tested; the GUI was tested offscreen, not in an on-screen session on every Windows version.

**PeterPiper 1.2.1.** The *Keep in step* correction is checked by `test_v121_sync.py` (16/16: the lab folder and folders inside it refused, also an unlinked folder holding a lab list; one's own folder and a folder holding the lab folder accepted; a 1.2.0 setting pointing into the lab folder writes no second copy, says why, and the lab copy is still kept in step; the window's note and refusal); the profile, start-screen, cloud and core suites were re-run (`test_v11_profiles.py` 74/74, `test_v11_start.py` 81/81, `test_v11_cloud.py` 106/106, `test_peterpiper.py` 40/40), all passing.

**PeterPiper 1.2.** Every developer test that could run on this computer was run on the 1.2 code (16 November 2026); all passed. **New in 1.2** (279 checks): the launcher and absorbing older versions (`test_v12_launcher.py`) 82/82 - the install-progress script with a stand-in for a slow pip (its output passed through, a *still working* line while it is quiet, its exit code returned unchanged, the package check one by one with the count), the reuse order of earlier installs, the launcher's routines run in a real `cmd.exe` in a folder with `&` and brackets; finding versions 1.0 and 1.1 through their folders, `.lnk` targets and `shortcuts_for.txt` in a made-up user folder, with PD4nav's folders, a newer version (nothing offered) and a developer copy (refused, its private Python kept) handled; the carry-over (never over an existing file, a run list merged); absorbing with a stand-in Recycle Bin - only program files and the private Python moved, the user's files kept and listed, the private Python the running version uses kept, a file in use, an open version or a failing move stopping that version, real `.lnk` files re-pointed - and one real Recycle Bin move of a temporary file; *Don't ask again*; the start-screen window once per start, not blocking, fitting 1366 x 768; loading bars (`test_v12_progress.py`) 57/57 - the time-left estimate on a stand-in clock, the working window and the analysis window's strip (percent, time, detail, a long path shortened in the middle without the window growing, a drive root's title, the older two-argument progress calls), and real callers sending fractions and details (folder searches, Compare's *Find my runs in a folder...*, AUTO-DETECT, tracking and export on the synthetic movie, reading a saved run, the recent analyses, saving graphs and comparisons); the Merge tool (`test_v12_merge.py`) 56/56 - on a built movie, touching ROIs and gaps of 1 - 6 px joined into one 4-connected ROI with a bridge only between the two (3 µm at 0.5 µm/px) and 7 px refused, the limit following the pixel size, a third cell in the gap never taken or blocking the merge, holes, cytoplasm and mitochondria measured pixels, ROIs at the image edge, the cells' other compartments; in the window, the button, the messages, Esc, the first cell's number kept, tracking cleared, no hand-drawn ROI counted, Undo, tracking the merged cell again (the other cells' numbers unchanged), SAVE and loading, the methods sentence, and no scroll bars at 1366 x 768, 1280 x 800 and 1366 x 700; the export folder and long paths (`test_v12_export.py`) 84/84 - the path arithmetic and shorter names (every planned path equal to the file a real export writes), *Save in* sending every output to the chosen folder while the autosave stays in the results folder, an unwritable folder refused, the long-path warning's buttons with long paths faked off (Shorten writing every file within the limit, Export anyway, Cancel writing nothing, another folder, *Turn on Windows long paths* with a stand-in for Windows' approval, approved and declined), the computer check's button, batch exports (names shortened by themselves and said in the log, one subfolder per movie) and Compare's *Close*. **Earlier suites**, re-run on the 1.2 code: the 1.1 suites (688 checks: start 81/81, analysis window 143/143, compare 46/46, profiles 74/74, cloud 106/106, looks 99/99, game 107/107, update 32/32), `test_peterpiper.py` 40/40, `test_v30.py` 75/75, `test_v29.py` 107/107, `test_graph.py` 160/160, `test_compare_groups.py` 62/62, `test_v26_kinetics.py` 49/49, `test_v25_track.py` 46/46, `test_gui_v25.py` 25/25, `test_rules_unit.py` 37/37, `test_v27_batch.py` 11/11, `test_pack_bat.py` 17/17 and its real install from the internet 31/31, `test_provenance.py` 39/40 (the one other check needs the lab's movies). Not run this time: the suites that need the lab's movies (`test_compare.py`, `test_history.py`, `test_gui_*.py`, `test_rules_track.py`, `test_graph_real.py`, `test_regress_v22.py`; the lab's drive was not connected) and the suites that open files in GraphPad Prism (`test_v27.py`, `test_v28.py`, `test_prism_live.py`, `test_prism_style.py`; a Prism window was already open, and the tests never touch a Prism they did not start); all of them passed on 1.1, whose measurement and export code 1.2 keeps. The analysis methods and every number are unchanged: 1.2 uses the same measurement, tracking, background, statistics and export arithmetic as 1.1; only the file and folder names of an export change, and only when you choose another folder or shorter names.

**PeterPiper 1.1.** Every developer test was run on the 1.1 code (15 November 2026, with the lab's movies), all passing. **New in 1.1** (688 checks): profiles, merge, keep-in-step and lab folder (`test_v11_profiles.py`) 74/74; storage & cloud, incl. a real Google Drive for desktop folder (`test_v11_cloud.py`) 106/106; colours, themes and accessibility - every theme's WCAG contrast, the cell palette's contrast and colour-vision-deficiency distances, cell colours identical in every theme (`test_v11_looks.py`) 99/99; start screen, movie queue and the hand-over between windows (`test_v11_start.py`) 81/81; analysis window - step pages, SAVE with a note, queue, events, Smart auto-select button, no scroll bars at 1366 x 768 and 1280 x 800 in both basic themes (`test_v11_mainwin.py`) 143/143; Compare - Open in analysis, output files, Save column (`test_v11_compare.py`) 46/46; Charlotte's Web - rarity rule (exactly 10 of 30 webs Rare/Epic), uniqueness of 200 webs, rendering time, the batch tray (`test_v11_charlotte.py`) 107/107; Check for updates against a stand-in for GitHub, never the network (`test_v11_update.py`) 32/32. **Earlier suites, unchanged results**: `test_peterpiper.py` 39/39; `test_v30.py` 80/80; `test_v29.py` 107/107; `test_v28.py` 54/54; `test_v27.py` 35/35 and `test_v27_batch.py` 17/17; kinetics 55/55; Compare runs 43/43; replicate averaging and the compare window 77/77; the V2.5 tracking features 51/51 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; session memory 57/57; trace panel and graph look 63/63; graph statistics 160/160 and on real measurements 9/9; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher 15/15. Tests changed on purpose: the analysis window now shows one step page at a time, so `test_v29.py` part D checks 'one step page at a time' instead of 'steps 1-2 open, 3-5 folded', and `test_gui_rules.py` opens the Track page before checking a tracking setting; the 1.1 suites written before an optional module existed start as if it were missing. The last change (Check for updates) was checked again with the start screen, analysis window, update and core suites. The analysis methods and every number are unchanged: 1.1 uses the same measurement, tracking, background, statistics and export code as 1.0.3, and every earlier test suite passes. Not yet checked: a real Mac screen.

**PeterPiper 1.0.3.** `test_peterpiper.py` part F (12 checks, on Windows; the Mac's portable tests run in the release build) uses a real folder that cannot be made: the reason is said in words (read-only drive, with the NTFS note for a Mac drive under `/Volumes`; no permission), the write test leaves nothing behind, Start with such a folder asks, *Cancel* keeps the start window and *Save the results there* uses and makes `PeterPiper results/OUTPUT_<movie>/<user>`, a writable folder is not asked about, the batch log moves there and earlier runs saved there are looked for. The other suites were run again on 12 November 2026 without the lab's movies (those tests say *SKIPPED - lab data only*; the V2.2 regression, the batch test on a real movie and provenance's real-data part need them and were not run), all passing: `test_v29.py` 107/107, `test_v30.py` 75/75, `test_v28.py` 54/54, `test_v27.py` 35/35, kinetics 55/55, replicate averaging and the compare window 77/77, the V2.5 tracking features 46/46, tracking rules 37/37, graph statistics 160/160, provenance 39/39, the Prism style field matrix with 0 failures, launcher 15/15, and the self-test 10/10. A batch run of the self-test's synthetic movie, placed where its `OUTPUT_` folder cannot be made, found and tracked all 16 nuclei and exported 14 files into `PeterPiper results/OUTPUT_<movie>`, its log saying why.

**PeterPiper 1.0.2 (the Mac app).** On GitHub's Mac machines (macOS 15, one Apple-chip, one Intel; Python 3.11.9 and the exact tested packages), the developer tests that do not need the lab's movies, GraphPad Prism for Windows or PD4nav's history all pass: `test_peterpiper.py` 24/24 (its real-console check is Windows only), `test_v29.py` 99/99, `test_v30.py` 75/75, tracking rules 37/37, graph statistics 153/153, kinetics 49/49, replicate averaging 62/62, `test_v28.py` 53/53 and `test_v27.py` 31/31; the self-test passes 10/10 from the code and **10/10 inside each finished PeterPiper.app** (every module, the complete `.nd2` reader, the logo; AUTO-DETECT finds the 16 synthetic nuclei, GFP F/F0 = 1.99 against a true 2.00, every export file type written and the workbook re-opened). The packaged Windows build passes the same self-test 10/10. Not yet checked: the Mac app on a real Mac with a screen, and a real `.nd2` opened in a packaged app.

**PeterPiper 1.0.** Every developer test was run again on the final PeterPiper 1.0 code (10 November 2026, with the lab's movies), all passing: the new `test_peterpiper.py` 27/27; `test_v30.py` 80/80; `test_v29.py` 107/107; `test_v28.py` 54/54; `test_v27.py` 35/35 and `test_v27_batch.py` 17/17; kinetics 55/55; Compare runs 43/43; replicate averaging and the compare window 77/77; the V2.5 tracking features 51/51 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; session memory 57/57; trace panel and graph look 63/63; graph statistics 160/160 and on real measurements 9/9; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher 15/15. The comparisons with V2.2's code read it from PD4nav's history (`dev_tests/pd4nav_history.py`) and still agree. **The new name and the logo** (`test_peterpiper.py`): no 'PD4nav' left in the app's own text except where it means PD4nav; a session saved now names the app and lists as 'PeterPiper 1.0', PD4nav's files as 'PD4nav 3.0' (same content keys, so an unchanged analysis is still recognised); new sessions in `PeterPiper_sessions`, PD4nav's `PD4nav_sessions` still read; a trained auto-detect, saved settings and an exported profile made by PD4nav load; a fresh start takes nothing from PD4nav (left untouched); the logo in the start windows (white on the dark theme, black on the light one, following a theme change); the icon at 16 - 256 px; and the launcher's logo **in a real console window**, read back from the screen: the window's width read (120 columns), the 116-wide art chosen and every line shown exactly with no garbled character. That check was added after the first launcher showed the plain heading (it read the window's height as its width) and, once fixed, stray marks where UTF-8 characters were cut (the art is now UTF-16) - both invisible to tests run without a window. Tests changed on purpose: the run-list label names the app ('PD4nav 2.2'); new sessions are expected in `PeterPiper_sessions`; PD4nav's V2.9 profiles are expected NOT to be taken over.

**V3.0.** Every developer test was run again on the final V3.0 code (8 November 2026), all passing: `test_v30.py` 80/80; `test_v29.py` 107/107; `test_v28.py` 54/54; `test_v27.py` 35/35 and `test_v27_batch.py` 17/17; kinetics 55/55; Compare runs 43/43; replicate averaging and the compare window 77/77; the V2.5 tracking features 51/51 with the real U2OS movie and the main-window features 25/25; provenance 47/47; tracking rules 37/37 and 33/33; GUI tracking rules 84/84; ROI / session files and run index 59/59; session memory 57/57; trace panel and graph look 63/63; graph statistics 160/160 and on real measurements 9/9; Prism look into `.prism` 52/52 and the Prism style field matrix with 0 failures; the V2.2 click-workflow regression 31/31; launcher 14/14. **Known answers** (`test_v29.py`, the shipped synthetic movie): AUTO-DETECT finds its 16 nuclei; the 8 sensor cells' GFP F/F0 after the step is 2.02 (true 2.00 - the drifting disc on the pixel grid), the 8 untransfected cells are left out of F/F0 and R/R0 by the ratio check; on numbers with a known answer the ratio check leaves out exactly the dim cells and the single timepoints where a denominator collapses, k = 0 switches it off and results without a recorded noise are untouched. The workbook's ratio-check formulas were calculated in Microsoft Excel and agree with Python cell for cell. **Helper channels and trained auto-detect** (`test_v30.py`): the helper image is exactly the main channel + 0.5 × each helper (each scaled, max difference 0.0002 counts); on a built movie whose helper blob is twice as wide, every frame's outline stays within 1 µm of the main channel's own outline; on the synthetic movie the helper rule gives the same outlines and numbers as the plain rule, the helper's signal separates the 8 sensor cells (≥ 131 × noise) from the 8 untransfected ones (≤ 1.4), and AUTO-DETECT with GFP as helper picks exactly the 8; a clicked cell without helper signal is kept with a note; older rules load and are applied exactly; the detector learns the 8 (held-out F1 1.00), leaves a limit that makes no difference off, takes quiz answers, never asks twice, is saved / listed / refused overwriting, and its button sets the rule and picks the 8; while scrubbing, the frame you stop on is read first and frames passed over are skipped, and closing waits for a read in progress; the baseline-drift workbook of a 4-channel run (32 quantities, columns past Z) is written with each slope equal to its least-squares line; uneven gaps between timepoints are found on known time stamps, written into the Methods and the Settings sheet with the recorded total, a movie with even gaps gives the same Methods text as before, the time axis stays even, and the start window warns on the lab movie whose first frame came 3 h 17 min before the rest; the detector is kept in the ROI file and named with its rule and score in the methods. On the lab's 8 hand-analysed biosensor movies (each scored by a rule learned from the other 7) it found 94 of 142 hand-picked cells with 56 extras (F1 0.66) against plain AUTO-DETECT's 91 with 154 extras (F1 0.50); trained on them, it picked exactly the 6 cells chosen by hand on a ninth movie (the user's example). **Unchanged arithmetic**: with the ratio check off, every CSV is byte-identical to V2.2's (synthetic and real data, the new SD column aside), and every F/F0 and ratio formula in the workbook (540 synthetic, 5,490 real) is exactly the V2.2 formula inside the ratio check. On the lab's U2OS movie the check (k = 5) took the largest R/R0 from 678 to 18. **Other checks** (V2.9 and V3.0): both themes; the built-in AUTO-DETECT limits of every earlier version (old 'learned' settings ignored; *Learn from my runs* retired after it gave only F1 0.61 -> 0.64 on 30 real runs); mean ± SD everywhere (a saved SEM moved to SD once; every preset names its error; Prism draws SD error bars across dishes - checked in Prism 11); no automatic background in the main window, TRACK leading to placing it, a run with an automatic background flagged on loading; the step bar (Rules current until looked at, folding); fading notes; shorter export names and the long-path estimate and warning (a 277-character real path becomes 224 with a user folder); user profiles (first user takes the old data, later users empty, own settings / run list / results folder, own runs only, rename keeping old runs, remove hiding without deleting, don't ask again, the move of V2.9 profiles to `%USERPROFILE%\PD4nav data`); portable profiles (export to a zip, import as a new user and again merged without overwriting, a pasted profile folder recognised, an unsafe zip refused, runs found again on 'another computer' by exact match and the new place remembered, missing runs kept); Compare's Find my runs in a folder; loading bars; the display copy for playback; the computer check; `build/set_github.py` (only PD4nav's own citation changes). Tests that need the lab's movies say *SKIPPED - lab data only* without them. Tests changed on purpose: SD instead of SEM where a test relied on the default; the comparisons with V2.2 run with the ratio check off and set aside the SD column, the Noise sheets and MinSNR; Prism cell lines counted for the cells that have values; the earlier GUI tests place the background automatically as before; a missing run is kept in the run list; a too-long export answers the new warning; the GUI tracking-rule tests set the older ONLY / WITH / AND / IF rules the way a run made before V3.0 brings them (same checks, same results); the folded Rules step is checked for its shorter V3.0 note.

## 13. Known limitations

- **WITH / AND / IF with the measured sensor as channel B.** Under WITH and AND the measured pixels depend on channel B's brightness (since V2.5 the followed outline itself no longer does), and under IF the choice of cells does. If channel B is the sensor whose response you measure, the ROI (or the cell selection) can depend on the response itself. Prefer an ONLY rule on a response-independent channel (a nuclear stain, a fill) for quantification, and use WITH / AND / IF with B = sensor only when that is what you intend - and say so in the methods.
- **AND can be lenient on low-noise cameras.** The noise is the MAD of integer counts; for many sCMOS / EM-CCD movies the MAD is exactly 1 count, so the noise is 1.48 counts and k = 3 means about 4.4 counts above the local background of smoothed B - nearly every pixel of a cell passes (99.96% on a colocalised mitochondria movie). Raise *AND rule: pixel threshold* in step 3 (`overlap_k`, e.g. 10 - 30; the k sweep in section 12 shows the effect) and check the kept pixels on the drawn timepoint.
- **First-frame size step.** The drawn timepoint is held within ±10% of what you drew, later timepoints within ±25%, so the area can step by up to about 15% between the drawn timepoint and the next (5.9 - 14.9% in tests of V2.3, the same in V2.2). Intensities are means, so this matters only where an ROI's edge changes what is averaged. With *Size may change by* 0% there is no step: every timepoint has exactly the drawn pixel count.
- **Hard size limits shape the outline.** When a redraw is outside the limits, the ROI is trimmed to its brightest connected pixels or grown by its brightest neighbours. This keeps the size, but the kept pixels are biased towards brighter pixels of the rule's channel A - if channel A is also the measured sensor, prefer a generous *Size may change by* (or a response-independent channel A).
- **Mitochondria timepoints without detectable mitochondria** measure the whole envelope region at that timepoint (usually also flagged by QC as an artefact).
- **One background region per movie**, no per-cell local background. Since V2.5 the region includes non-transfected cells by design and **every pixel of it is used** - a bright, dead or passing cell in the region raises the background at those timepoints. The fluctuation check reports such jumps (more than 5 robust SD **and** 5% of the level) and drift (over 20%) but never corrects them: redraw the region if it is not steady. Smaller or slower changes are not flagged. For a region you choose, avoid areas with debris or bright cells.
- **Tracker boundary lines are stored by cell number.** If you move an ROI to another cell or split a cell, the lines belong to the cell number, not to the ROI; check the orange lines after such changes. Lines are fixed in the image: a cell that moves far may need its lines redrawn (or no lines).
- **Replicate averaging uses only common frame times.** Dishes imaged at different intervals or for different lengths are averaged only at the times all of them have (no interpolation); with incommensurate intervals few or no times may remain - the window says so.
- **Cell-line colours** are recognised from names only; shades are per colour family, so two different cell lines of one family (e.g. HepG2 and Huh7, both liver blues) get shades of the same colour. Change a colour by double-clicking it (remembered).
- **Movement model**: one rigid translation per cell per timepoint (integer pixels, sub-pixel remainder carried), measured around the lead ROI, at most `max_move_um` (3 µm) per timepoint; faster cells, rotation and cells crossing each other may need re-drawing. Cell division, death or cells leaving the field are not modelled.
- **Prism style.** The live look is written into the `.prism` files, but a few looks Prism cannot draw get the closest Prism look (section 9.4, brown note); a style file of your own that was not made from a PeterPiper `.prism` keeps its own look. Graph-look settings you changed in an earlier version are kept; those still at the old defaults take the template values once.
- **Prism 10 untested**: `.prism` files were verified with Prism 11 only; Prism 9 or older cannot open `.prism` files - use `.pzfx`.
- **Windows 10 / 11 and macOS 14+**; on Windows, 64-bit Python 3.11 - 3.14 for the exact tested packages (3.10 with compatible versions).
- **Long paths.** Exports handle paths over 260 characters, but some other Windows programs cannot open files in very deep folders - keep the data folder reasonably short. The install folder must be short (≤ 85 characters) unless Windows long paths are turned on. 1.2: with long paths off, the export warns and offers shorter names (section 6.7); with long paths on, there is no warning, although Excel still does not open a workbook whose path is over 218 characters. After *Shorten names for me* the file names no longer carry the whole *Name for the files* (the graph titles do).
- **Turn on Windows long paths was tested with a stand-in** (1.2): the developer tests replace Windows' administrator approval and the registry with stand-ins; the real approval prompt and the real change of the setting were not exercised by the tests. Some programs see the change only after Windows is restarted.
- **Absorbing older versions on a Mac is untested** (1.2): the Recycle Bin, shortcut and in-use checks were tested on Windows only; moving to the Mac's Trash was not tested.
- **Merge does not keep the second cell's tracker boundary lines** (1.2): the merged cell keeps the first cell's lines only; redraw lines for it if needed (section 6.5). The second cell's include / exclude choice is dropped too (except for a compartment only it had).
- **Some parameters are not in the window**: `mito_k` and the QC thresholds - edit `settings.json` with PeterPiper closed (the largest movement and the IF / AND thresholds are in step 3 since V2.4). The values used are always recorded in the exports.
- **Nucleus click fallback**: where no nucleus is found under a click, a circle of typical nucleus size is placed - check it.
- **Fingerprint**: changes in the middle of an `.nd2` larger than 8 MiB are not detected.
- **AUTO-DETECT** is conservative and tuned on the lab's images; it may propose nothing on unusual images - click instead. Its brightness slider ranks on the timepoint shown; if you drop the dimmest cells, say so in the methods (it is an inclusion criterion).
- **Tracking made before V2.5** keeps its original background values when loaded; only re-tracking gives the V2.5 background and the sums.
- **Tested offscreen**: the GUI tests ran without a visible screen; wording and layout were reviewed on a real screen less systematically.
- **Not yet tested on a real Mac screen** (1.1): the Mac app is built and self-tested on GitHub's Mac machines, but the 1.1 windows have not been checked on a Mac with a screen.
- **No scroll bars only at the default text size** (1.1): the start screen, the analysis window and the Compare window are laid out to fit 1366 x 768 without scroll bars at the default text size; larger text may need scrolling.
- **Smart auto-select learns nucleus selection** (1.1): it proposes nuclei; other compartments follow from your tracking rules. It reproduces the selections it learned from - consistent hand-picking makes a consistent rule - and its held-out F1 is the expected agreement on new movies of the same kind, not a guarantee. Always review its proposals.
- **Cloud folders are found by their default locations** (1.1): *Storage & cloud* recognises the services' default folders (and, on Windows, read-only registry entries); a folder in an unusual place is not listed, but can be chosen with *Other folder...*.
- **Keeping profiles in step relies on roughly correct clocks** (1.1): where both copies changed the same single value, the newer change wins, judged by file times and recorded change times on each computer.
- **Union merging can bring back a deleted value** (1.1): merged and synced profiles are united, so a colour, setting or list entry deliberately deleted on one computer can come back from another copy that still has it.

## 14. Troubleshooting

**Messages from `PeterPiperV1.2.bat`**

| Message | What to do |
|---|---|
| "PeterPiperV1.2 cannot run from inside the zip file." | Close the window, right-click the zip > *Extract All...*, open the extracted folder and double-click `PeterPiperV1.2.bat`. Extract somewhere simple like `D:\PeterPiperV1.2` (not OneDrive, not a network drive). |
| "Python is not installed on this computer." | Install 64-bit Python 3.13 (or 3.12 / 3.11) from https://www.python.org/downloads/windows/ - tick "Add python.exe to PATH" on the first screen - then double-click the `.bat` again. |
| "This computer's Python cannot run PeterPiperV1.2: Python 3.x" ... "needs 64-bit Python 3.10 - 3.14" | The Python found is too old, too new or 32-bit. Install 64-bit Python 3.13 as above. |
| "The install folder's path is too long for Windows (over 85 characters)" | Set `PETERPIPER_HOME` to a short folder (e.g. `C:\PeterPiper`), or ask IT to turn on Windows long paths, then try again. |
| "Could not set up the private Python" | Usually the folder is on OneDrive or a network drive: move the PeterPiperV1.2 folder to a local drive (e.g. `D:\PeterPiperV1.2`). If antivirus showed an alert, check it with IT first. |
| "The exact tested versions could not be installed on this computer ... Trying the compatible versions instead" | Nothing to do; the program will work. For published work, note the versions in `installed_versions.txt` (or install on a computer with Python 3.11 - 3.14). |
| "NOTE: this computer got COMPATIBLE package versions" | As above - report `installed_versions.txt` for published work. |
| "Downloading the packages failed" | Usually no internet or a firewall blocking pypi.org. Fix the connection and double-click again (it carries on). If it keeps failing, delete the folder it names (`...\.PeterPiperV1.2\venv`) and try again. |
| "PeterPiperV1.2 closed unexpectedly. Opening the error report ..." | Notepad opens `error_<number>.txt`: send it to whoever maintains PeterPiper. |
| The black window flashes and closes / nothing happens | Run the `.bat` again and read the message; check that the folder is extracted and local. |
| "still working - ..." lines, and the text stops for minutes at "Installing collected packages" | Nothing to do: pip is still working (1.2: a *still working* line comes whenever pip is quiet for 5 s). Do not close the window. |
| 1.2 installs again although PeterPiper 1.1 is installed | The 1.1 install is reused only if its package list is byte-identical and its Python still starts (section 3.2, step 4); otherwise 1.2 makes its own install (once). |

**In the program**

| Problem | What to do |
|---|---|
| "Something went wrong" / "unexpected error" box | The window usually stays usable; *Show Details...* has the technical text to send to the maintainer. Your work is autosaved. |
| *Older PeterPiper versions are on this computer* (1.2) | Absorb, Not now or Don't ask again for these (section 3.8). Your profiles and runs are already in `PeterPiper data`; absorbing only tidies up the older program files, its private Python and its shortcuts. |
| Absorb: "PeterPiper 1.x seems to be open - close it, then try again" / "a file in it is in use" | That version (or a file in its folder) is open. Nothing of it was moved. Close it and restart PeterPiper 1.2 (the window comes back unless you chose *Don't ask again*). |
| Absorb: "the drive of ... has no Recycle Bin" | The older version is on a drive without a Recycle Bin (e.g. a network drive), so PeterPiper does not move it (it would be deleted for good). Delete it by hand if you no longer need it. |
| Absorb: "kept: PeterPiper 1.2 uses it" | PeterPiper 1.2 runs on that version's private Python (section 3.2, step 4), so it stays. |
| Absorb moved something you still need | Everything moved is in the Recycle Bin: restore it from there. |
| Merge: "These two ROIs are not next to each other" | Only ROIs that touch or are up to 3 µm apart can be merged. Click the ROI next to the first one, or use *Add to cell* / *Draw by hand*. |
| Merge: "Another cell lies between these two ... ROIs" | Joining them would take another cell's pixels. Remove or move that cell's ROI first, or leave them as two cells. |
| Merge: "Cell N and cell M each have a nucleus, and those are not next to each other" | One cell holds one ROI per compartment. Remove one of the two nuclei (or right-click it > make it a cell of its own), then merge. |
| *Long file paths* when exporting (1.2) | *Shorten names for me* (the default) is usually right; *Choose another folder...* higher up (e.g. `C:\Results`) keeps the full names (section 6.7). |
| *Turn on Windows long paths*: "Not changed: Windows' administrator approval was not given" | This account is not an administrator, or the approval was declined. Ask IT to turn on the Group Policy *Enable Win32 long paths* (`LongPathsEnabled` = 1), or shorten the names. |
| "Cannot save there" (export list, batch window) | PeterPiper cannot write in the chosen folder (read-only, full, no permission or disconnected): choose another, or *Usual folder*. |
| "Could not open the file" | The `.nd2` is damaged, still being written, or on a disconnected drive. Copy it locally and try again. |
| "No clear nucleus / whole cell at that spot" | Click nearer its middle, check the tracking rule (step 1) - is the compartment visible on channel A? - or use Draw by hand. |
| A nucleus came out as a circle | Nothing was found under the click (section 8.2): Undo and click again, or draw it by hand. |
| "That spot is already covered by cell N's ..." | Another cell's ROI is there; click a different cell or Remove that one first. |
| Outlines do not follow a cell | Check the lead rule (the first rule's compartment should be clearly visible); redraw that cell; for fast-moving cells raise *Max movement between timepoints* in step 3; exclude the cell if it cannot be followed. |
| ROI grows into a neighbour | Lower *Size may change by*; make sure the neighbour has its own ROI (rivals are kept apart); draw a **Tracker boundary** line between the two cells. |
| Two touching cells swap or merge | Draw a **Tracker boundary** line for each of them (click the cell, click the points of the line, double-click), then TRACK & MEASURE again. |
| Orange lines are on the wrong cell | Lines belong to a cell number (section 6.5): select the cell, **Remove lines**, and draw them again for the right cell. |
| "The background region is not steady: ... jumps at timepoint(s) ... / drifts by ... / measured cells cover up to ..." | The background of a channel jumped at the timepoints named (usually a bright, dead or passing cell in the region), drifted over the movie, or tracked cells lie in the region. Every pixel was used as it is; nothing was changed. Scrub to those timepoints and look at the green box. To fix it, press **Redraw background** (or choose Compartment *Background* > *Draw by hand*), draw the region somewhere steadier and TRACK & MEASURE again; **Keep it** if the change is real or small. |
| "No place for a background region was found - draw it by hand." | The image has no 25 µm square free of ROIs and bright objects: choose Compartment *Background* and Add or Draw by hand. |
| AUTO-DETECT found too many dim cells | Move the slider under AUTO-DETECT to the left: the dimmest are removed first. |
| Compare: "These dishes have no frame time in common" | The dishes were imaged at intervals with no common frame time (or the times do not overlap): put them in separate groups or compare them as *Each run*. |
| Compare asks for a colour | The cell line was not recognised in the name: pick a colour (remembered for that name), or rename the run / group with the cell line in it. |
| Graphs still look like V2.4 (black line, small font) | A graph look saved in an earlier version was carried over: Look > *Prism default - mean ± SEM*, and set the font size to 18 in *More style...*. |
| AND keeps almost every pixel | Raise *AND rule: pixel threshold* in step 3 (`overlap_k`, section 13). |
| IF excludes a cell you want | Tick it in the cell list; it is then included (your choice is saved). |
| "No tracking to show" when loading | The file has no usable tracking (the reason is shown); answer Yes to "Track now?". |
| "Different image size" | The ROI file belongs to another movie. |
| "The results cannot be saved there" (start window); *Read-only file system* | The movie's drive cannot be written: on a Mac, usually an external drive formatted for Windows (NTFS) - macOS reads it but cannot write to it (Finder > the drive > *Get Info* says *You can only read*). Click *Save the results there* (your `PeterPiper results` folder) or *Choose another folder...*; the movie can stay on the drive. A full drive or a folder without permission gives the same message. |
| "Could not save your work automatically" | Usually the results folder is read-only, full or on a disconnected drive. Reconnect or free the drive (or fix its permission) and press SAVE again - keep the window open meanwhile, so nothing is lost. For later movies choose a writable results folder (start screen *Results folder > Change...*, or *Storage & cloud*). |
| Raw TIFFs look black | Windows Photos shows raw 16-bit images almost black; open them in Fiji / ImageJ, or use the viewing copies. |
| Excel shows no values in the derived sheets | Open the file in Excel or LibreOffice (not a CSV reader); in Excel's Protected View click *Enable Editing* so the formulas calculate. |
| Antivirus alert | Stop and check it with IT; do not allowlist the folder without checking. |
| OneDrive folders | Do not install or run PeterPiper from OneDrive; for data, make sure files are downloaded locally ("Always keep on this device"), because reading a cloud placeholder is slow or fails. |
| Text too small / too big | *View > Larger text* (Ctrl +), *Smaller text* (Ctrl -), *Normal text size* (Ctrl 0); on the start screen `A-` / `A+`. Remembered. |
| The side panel is cut off | 1.1: the analysis window shows one step at a time and fits 1366 x 768 at the default text size; make the text smaller (Ctrl 0 for the default) or the window larger. |
| *Smart auto-select (locked)* | It unlocks after you draw the cells by hand (at least one ROI added by hand) on 3 movies of a movie queue and press SAVE on each (section 6.15). Hover over the button for the count so far. |
| *Smart auto-select (no bin for these channels)* / "No bin has the channels of this movie yet" | Open your bins (the button, or step 2 *More > Smart auto-select: your bins...*) and put hand-drawn movies with these channel names into a bin (*New bin...*). A bin needs at least 2 hand-picked movies whose run file and `.nd2` are on this computer. |
| "This movie is stored only online ... it will be downloaded first" | The `.nd2` is a cloud placeholder (OneDrive, Google Drive, iCloud ...). Let it download (it can take a while for large movies), or make it available offline in the service's app first ("Always keep on this device"). |
| The lab folder is read-only | This computer can read the lab folder but not write to it (permissions, or the cloud app is not syncing): the lab list is used as it is and changes are not saved there. Ask the lab's admin or IT for write access. |
| Forgotten password | An admin can reset it (*Lab settings...* or the user list); on a single computer, deleting `password.json` in that user's folder (`PeterPiper data\users\<name>\`) also removes the password. Nothing else of the profile is affected. |
| Emoji (✨, 🔒, 🕸) show as empty boxes | The computer has no emoji font; only the symbols are affected. On Windows the *Segoe UI Emoji* font is normally present. |
| A movie from the queue (or a run list) opens the start screen instead of the analysis window | Its metadata needs a look (no pixel size or the 1.0 µm/px stand-in, no frame interval, uneven gaps, several stage positions, or unusable channel names): the start screen says what; check it and press *Open in the analysis window*. |
| *Check for updates*: "Could not reach GitHub (no internet, or it is blocked here)" | No internet connection, or a firewall / proxy blocks GitHub. Nothing was changed. Try again later or download the new version from the Releases page. |
| *Check for updates*: "This is a developer copy" | The program folder is a git checkout: update it with git; *Check for updates* never changes it. |

## 15. Version history

**PeterPiper 1.2.1** (this version, 16 November 2026) - a correction to *Keep in step*; the methods and the numbers are unchanged. The same program folder as 1.2.0 (`PeterPiperV1.2`), so *Check for updates* updates 1.2.0 in place.

- *Keep in step* no longer accepts the lab folder, or a folder inside it, as a person's own folder: the lab folder already keeps every profile in step (`PeterPiper profiles`), so the person's profile was copied twice into the lab's shared folder. The window now says when the lab folder covers the profile; a 1.2.0 setting that points into the lab folder is no longer used (said in the note), and the lab folder's copy carries on (section 6.16).

**PeterPiper 1.2.0** (16 November 2026) - the methods and the numbers are unchanged (the same measurement code; every earlier test suite passes, section 12). New:

- **Merge** (sections 6.4, 8.2): a tool for two ROIs next to each other that are really one cell. Click one, then the other: they become one ROI with the first one's number, joined by the smallest bridge between them (never on another cell's pixels), holes closed by the join filled; refused for ROIs more than 3 µm apart or with another cell between them. The cells' other compartments are merged the same way. Tracking is cleared; Undo restores both. The methods text says that ROIs could be "resized, split, merged, extended or drawn by hand". The ROI tools now stand in two rows.
- **Where an export goes** (section 6.7): *Save in* in the export list, with *Change...* and *Usual folder*; the export goes to `<chosen folder>\Export_<date>_<time>`, an unwritable folder is refused, autosaves and SAVE stay in the results folder, and the choice is kept for the movie's next export. Batch analysis has *Save exports in* (one subfolder per movie, section 6.12).
- **Paths too long for Windows** (section 6.7): with Windows' long paths off, an export whose paths would be too long for Explorer (259 characters) or Excel (218) offers *Shorten names for me* (the default; the middle of the name is cut, the export folder may get the short name `Export_<yymmdd>-<hhmm>`), *Show Details...*, *Choose another folder...*, *Turn on Windows long paths* (Windows' own administrator approval), *Export anyway* and *Cancel*. Batch runs shorten by themselves and say so in their log. Graph titles keep the full name. *Help > Computer check...* has the same *Turn on Windows long paths* button.
- **Loading bars** (section 6.2): every working window and the analysis window's progress strip show the percent (or a moving bar when the amount is not known), the time left ("about 1 min 20 s left", "estimating time left...", "almost done") or the time so far, what is happening and a detail line naming the file, folder or count (shortened in the middle; whole on hover); a finished strip says how long it took. Folder searches give a real fraction, saving and exporting name each file, and reading a saved run, the recent analyses, adding several runs in Compare and a batch folder have bars too. Window titles are never empty (a drive root is named in full).
- **Launcher** (section 3.2): an identical earlier install (PeterPiper 1.1, then 1.0, then PD4nav's) is reused, so 1.2 opens at once on a computer with 1.1. While installing, a *still working* line every 5 s of silence says what pip is doing, how long it has taken and roughly how long is left (`app\install_progress.py`, standard library only); the packages are checked one by one with a count; each step and each start says how long it takes. pip's own download bars now appear when each download has finished, not while it runs. A real install took 132 s.
- **Taking in older versions** (section 3.8): once per start, the start screen offers to absorb older PeterPiper versions (1.0 and later; never PD4nav): what they kept for themselves is copied into `PeterPiper data` (nothing overwritten), the Desktop and Start-menu shortcuts start 1.2, and their recognised program files and private Python go to the Recycle Bin (restorable). The user's own files, developer copies, the private Python 1.2 uses, the running program and `PeterPiper data` are never touched; an open version is left alone. *Not now*, *Don't ask again for these*; `PETERPIPER_NO_ABSORB=1` turns it off.
- **Compare window**: a *Close* button at the bottom right.
- Own program folder and launcher `PeterPiperV1.2` / `PeterPiperV1.2.bat` and install folder `%USERPROFILE%\.PeterPiperV1.2` (the same package versions as 1.0 and 1.1); users and runs in `PeterPiper data` carry over. Mac: `PeterPiper-1.2.0-macOS-AppleChip.dmg` / `-Intel.dmg`.

**PeterPiper 1.1.0** - the methods and the numbers are unchanged (the same measurement code; every earlier test suite passes, section 12). New:

- **A new start screen** (section 6.1): opens maximized, no scroll bars at 1366 x 768; big choices *Analyse movies* (one `.nd2`, or several at once - a movie queue), *Continue your queue (N left)* and *Compare / average saved runs*; a movie card with every earlier check (pixel size, frame interval, uneven gaps, stage position, channel names, results folder with *Open results folder*, analysed before, read-only drives); tabs *Recent analyses* (open a run straight into the analysis window) and *Queue*; a footer with *Saved files*, *Storage & cloud*, *Check for updates*, *More*, text size and theme; the Smart auto-select status line. Movies opened from the queue or a run list skip it only when their metadata is complete.
- **A redesigned analysis window** (section 6.2): opens maximized; one step page at a time; **SAVE** (with an optional note) and **EXPORT** always at the foot of the panel; a top row with *Another file*, *Open results folder*, *Compare*, *Undo* and, in a queue, *Movie 2 of 5*, *Skip*, *Next movie*; *File > Back up this analysis...*; *Help > Check for updates...*; *Help > Achievements...* once something is found.
- **SAVE and the movie queue** (section 6.14): SAVE writes a saved ROI file with the tracking (kind `saved`) and your note, shown in Compare as *Saved: <note>*; queued movies are *to do* / *saved* / *exported* / *skipped*, kept per user; *Next movie* asks to SAVE first if needed. The autosave is unchanged.
- **Smart auto-select** (sections 6.15, 8.13): cell selection learned from your own hand-picked movies, in named bins (one per kind of experiment); n hand-picked movies on the button and, with the ROI count and the held-out score, in the methods text of every run that used it. Unlocked by hand-drawing and SAVEing 3 movies of a movie queue. Plain and trained AUTO-DETECT are unchanged.
- **Compare window** (section 6.10): eight buttons instead of twenty (menus *Add runs*, *Groups*, *Output files*, *List*, *More*), opens maximized, a clearer list with the new columns *Save* and *User*, **Open in analysis** (finds the run's movie and checks its fingerprint), *Open results folder* and *This run's output files*.
- **Profiles and lab** (sections 6.0, 6.16): a redesigned *Who is using PeterPiper?*; **Merge profiles** (two spellings, or a profile from another computer; nothing deleted, the merged name becomes an alias); **Keep in step** through your own cloud or network folder; a **lab folder** with one lab user list, aliases, profiles and the lab's data folders for every linked computer; roles **User / Admin / Developer**; **optional passwords** (salted PBKDF2-SHA256 hash only).
- **Storage & cloud** (section 6.17): results next to each movie or in a folder of your choice, e.g. in OneDrive, Google Drive, Box, Dropbox or iCloud Drive (through the services' own apps - PeterPiper never signs in); **Back up this analysis** without ever overwriting; a warning when a movie is stored only online.
- **Colours and accessibility** (section 6.18): colour-blind-safe cell colours, the same in every theme, with line styles beyond six cells; a white trace plot in every theme; colour swatches in the cell list; every theme checked against WCAG 2 contrast minimums (the basic themes adjusted slightly); 18 optional colour palettes as a hidden extra.
- **Check for updates** (section 3.6): on request only - asks GitHub's public release list, then updates changed program files in place (backups kept), unpacks a new version into its own folder, or (Mac) downloads the right `.dmg`; never touches your data. This is the only network use in the program (section 4).
- **Charlotte's Web** (section 6.19): a small game that rewards hand annotation with a unique web per hand-picked movie; it never touches data, measurements or results. A few further optional hidden extras.
- Own program folder and launcher `PeterPiperV1.1` / `PeterPiperV1.1.bat` and install folder `%USERPROFILE%\.PeterPiperV1.1` (one install of about 5 minutes per computer; the same package versions as 1.0); users and runs in `PeterPiper data` carry over from 1.0. Mac: `PeterPiper-1.1.0-macOS-AppleChip.dmg` / `-Intel.dmg`.

**PeterPiper 1.0.3** - **movies on a drive PeterPiper cannot write to**. A drive formatted for Windows (NTFS, e.g. many external hard drives) can be read by a Mac but not written to, so the results folder next to the movie could not be made and *Start* ended in an error (*Read-only file system*). Now: if the movie's drive is read-only, the start window suggests a results folder on this computer at once (`PeterPiper results/OUTPUT_<movie>/<your name>` in your home folder); and before anything starts, PeterPiper checks that the results folder can really be written (on every system - also a full drive or a folder without permission) and, if not, says why in plain words and offers that folder or another one. The movie is only ever read, so it can stay where it is. A batch run puts each such movie's results there (the log says so), and the batch log too; *Compare* saves there instead of the home folder; earlier runs saved there are found when the movie is opened again. The methods and the numbers are unchanged.

**PeterPiper 1.0.2** - **PeterPiper for Mac**: a self-contained `PeterPiper.app` for macOS 14 or newer, for Apple-chip and Intel Macs (section 3.7) - drag it into Applications and double-click; it carries its own Python and the tested package versions, so nothing has to be installed. It is the same program as on Windows, built for each release on GitHub's Mac machines, where the developer tests run on macOS and the finished app checks itself. New for both systems: `PeterPiper --selftest` (a whole analysis of a built-in synthetic movie with known answers, and optionally a real `.nd2`), and *Compare* recognises the same `.nd2` whatever the case and slash direction of its saved path on every system (a run saved on Windows can be compared on a Mac). On Windows nothing else changes (same launcher, same install).

**PeterPiper 1.0.1** - changes from 1.0.0: the program works exactly as 1.0.0 (same methods, same numbers). The project's Zenodo DOI is in the citation, the README and *About PeterPiper*; the manual's example names no longer name the lab's sensor; and the developer tests no longer contain the lab's own file names and folders: they read them from a local list that is never uploaded (`dev_tests/lab_paths.json`, see `CONTRIBUTING.md`), and the test logs are no longer kept in the repository.

**PeterPiper 1.0.0** - PD4nav is now PeterPiper; changes from PD4nav V3.0 (the methods and the numbers are the same):

- **The new name** everywhere: window titles, the files PeterPiper writes, the Methods text and this manual; the program folder `PeterPiperV1.0`, the launcher `PeterPiperV1.0.bat`, the code package `peterpiper`.
- **The logo** at the top of the start window and *Who is using PeterPiper?* (black on the light theme, white on the dark), as the window and taskbar icon, and drawn in block characters in the launcher's window at the first install and at every start (section 3.2).
- **PeterPiper shortcuts** with the logo icon next to the `.bat`, on the Desktop and in the Start menu, made by the launcher (section 3.2).
- **A fresh start on every computer**: nothing is taken over from PD4nav, whose data is left untouched; a PD4nav profile can be imported on purpose (section 3.6).
- Files PeterPiper writes **name the app**, so lists of earlier analyses and Compare say "PeterPiper 1.0" or "PD4nav 3.0"; everything PD4nav saved (ROI and session files, `PD4nav_sessions`, saved settings, trained auto-detects, exported profiles) is still read. New sessions go to `PeterPiper_sessions`.

**V3.0.0** (PD4nav's last version) - changes from V2.9:

- **Helper channels instead of ONLY / WITH / AND / IF** (section 6.3): *Auto-detect [compartment] using [main channel]*, *+ helper channel*. Helpers choose which cells AUTO-DETECT picks (they need the helper's signal) and help follow them (main + 0.5 × each helper; the outline stays within 1 µm of the main channel's own outline). Runs made with the older rules load and are applied exactly as saved.
- **Train auto-detect from my runs...** (section 6.13): learns which cells you pick from your hand-analysed runs, shows an honest score (each movie scored by a rule learned from the others) with green / red / yellow outlines, asks a keep / skip quiz about the blobs it is unsure of, and saves a named button under AUTO-DETECT (in your profile; its rule and score go into the Methods). On the lab's biosensor movies: two-thirds fewer extra cells than plain AUTO-DETECT.
- **Ratio check** (section 8.7): F/F0, ratios and R/R0 left out where a channel is below 5 × the noise of the ROI's mean at baseline (and single ratio values where the denominator collapses) - no more divide-by-almost-nothing spikes; adjustable, in every output.
- **Mean ± SD everywhere by default**; every ready-made graph look names its own error (*Prism default - mean ± SD* / *- mean ± SEM*, *Mean ± SD / SEM + each cell*, *Shaded SD / SEM band*, ...) (main window, exports, Prism, Excel - which now also has SD columns - and Compare, one shared choice); a saved SEM (the old default) became SD once.
- **Background picked by you**: no automatic background region when a movie opens (it often sat on cells); TRACK without one leads you to place it. Batch analysis still places it itself.
- **Shorter paths**: per-quantity files inside `OUTPUT_<movie>` no longer repeat the movie name; a warning before an export whose paths would be too long with long paths off.
- **Profiles** in `%USERPROFILE%\PD4nav data` (one folder for every version), Rename / Remove (nothing deleted), *Don't ask again on this Windows account*, Enter continues; Compare > *Find my runs in a folder...* for runs made on other computers.
- **Portable profiles**: Export my profile... / Import a profile... (merges, never overwrites), copied profile folders recognised, runs on other computers kept in your list and found again with Compare > *My data is in...* (exact match, new place remembered).
- Runs whose background was placed automatically say so when loaded (*Check the background*).
- A small synthetic test movie ships with the code (`dev_tests/data`), so anyone can run the tests; tests that need the lab's own movies say *lab data only* and are skipped without them.
- The step bar keeps *1 Rules* current until you have looked at the rules; the folded step shows the active rule.
- *Learn from my runs* (V2.9) was **retired**: on the lab's 30 runs it did not improve AUTO-DETECT enough to be worth its controls.
- GitHub-ready: `docs/PUBLISHING.md`, `build/set_github.py` (the repository address and DOI in one step), issue templates, `CONTRIBUTING.md`.
- **Scrubbing big movies**: the frame you stop on is read first (12.2 s -> 0.6 s after dragging across 60 frames of a 46 MB-per-frame movie not yet in memory); closing the window no longer crashes when a frame is still being read (section 8.3, *Display only: smooth playback*).
- **Uneven gaps between timepoints are shown** (section 6.1, step 2): from every frame's time stamp, in the start window, the Methods text and the Settings sheet, with the total as recorded. Times in the results stay evenly spaced (unchanged).
- **Export fix**: exporting with *Baseline drift* on failed for runs with more than 24 quantities (e.g. 4 channels with ratio sheets: 32) with *'[' is not a valid column name* - the drift workbook named its columns past Z wrongly (a bug since V2.2). Nothing else in the workbook changed.
- The window's *How to use* help describes helper channels and the background you place (it still described ONLY / WITH / AND / IF and the automatic background).

**V2.9.0** - changes from V2.8:

- **A new look**: two themes, **Midnight (dark, the default)** and **Daylight (light)** - *View > Theme*, or the start window; Segoe UI Variable text, cards for the steps, accent-coloured main buttons, drawn tick boxes and arrows; remembered.
- **Step bar and focus**: where you are (1 Rules - 5 Export), click to jump; steps you are not on fold to their title (*View > Fold finished steps*).
- **Quiet notes**: Saved / Exported / Graph saved fade away with *Open folder* instead of an OK box.
- **Smooth playback**: a half-size display copy made in the background for big movies (display only), the time line updated ~6 × per second while playing - about 3 × less work per frame.
- **User profiles** (section 6.0): who is using PD4nav is asked first; each user's settings, runs, groups and saved files in their own folder, results in `OUTPUT_<movie>\<user>`, only their own runs listed.
- **Loading bars** for everything slow (opening a movie, reading runs for Compare, ticking runs, saving a comparison, looking for earlier analyses); the Compare window opens about 6 × faster (each run file read once) and ticking many runs redraws once (5.8 → 0.5 s for 34 runs).
- *Learn from my runs*: AUTO-DETECT limits and keep / remove suggestions learned from your own runs, used only when you tick them (retired in V3.0).
- **Computer check** at the first start (long-path setting, Python version; section 6.0).
- The Compare time course has its **dashed baseline line at time 0** again (also in its saved pictures).
- Saving settings from a dialog no longer forgets the last folders; the *Check cells* button is no longer cut off.

**V2.8.0** - changes from V2.7:

- **Every measure, against any other**: raw intensity, background, ΔF/F0, ΔR/R0, sum intensity, area (µm²) and compartment ratios (e.g. nucleus / cytoplasm, raw and ÷ baseline), besides R/R0, F/F0, ratio and intensity; X = Time, Timepoint or any measure; a right Y axis also against a measure; a red line explains plots that make no sense (section 6.10).
- **Run list in folders by group**: each group a folder (dishes plotted, colour, tick for the whole group); the analyses of one `.nd2` in a movie sub-folder (newest first; one dish - one analysis per movie in the Groups modes); a *Movie folder* column tells same-named movies apart; *Version* = the PD4nav version that made the analysis.
- **Groups without typing**: *+ New group*, drag runs onto a group's folder (or *Put selected runs in*), rename, delete; a movie's analyses move together.
- **Mean ± SD by default** in the Compare window (remembered).
- **Saved files log**: every save listed, click to open (section 9.13).
- **Resizable**: draggable dividers that cannot hide a part, scrolling settings, a minimum window size; the Save options are in the Save dialog.
- Trajectories mark their start and end; dot plots show the mean ± error as a cross. Axis labels show the real values (no automatic ×0.001 scaling).
- **What is plotted is clear**: ticked runs bold with their colour, the rest dimmed; the panel shows what is plotted per group.
- **Graph controls**: Y / X error-bar toggles (Y only by default), *Each cell*, click a legend entry to hide a line, hover a point for its values, reset zoom.
- **Explanations on hover** for every measure, X choice, *Show* mode, kind of points, error and kinetics graph, written for someone new to the analysis.

**V2.7.0** - changes from V2.6:

- **Background warning only for a real problem**: the box now appears only when a bright object enters the background region (it raises the background by more than 3% of its level) or measured cells cover more than 5% of it. Lamp flicker, focus changes, bleaching and a few overlapping pixels no longer trigger it (they are still recorded). The background numbers are unchanged (section 8.4).
- **Plot builder** in Compare / average runs: *Plot [quantity] of [channel] (over [channel]) in the [compartment] vs [Time or another measure]*, with points per timepoint (trajectory, X and Y error bars) or per cell, and an optional right Y axis; remembered (section 6.10).
- **A graph for every table** in every `.prism` (section 9.4).
- **Prism style templates**: edit the look once in Prism, every `.prism` uses it, remembered; a column graph style for kinetics / drift tables (section 6.11).
- **Saved settings** (analysis and plot conditions as named files) and **batch analysis** of many `.nd2` files, and batch saving of plots (section 6.12).
- Automatic Prism axes also get an automatic tick interval; the automatic background message no longer says objects are 'left out' (nothing is, since V2.5).
- **Published under the MIT license**, with `CITATION.cff` and `CHANGELOG.md` (section 17).
- Carried over at the first start: settings, compare colours and window choices from V2.6 (then older); the run indexes of V2.6 - V2.3 are merged.

**V2.6.0** - changes from V2.5:

- **Compare / average runs remembers your work**: each run's group (by run file and by `.nd2` fingerprint, so a new analysis of a grouped dish joins its group), its name in the graph, the ticked runs, the mode, compartment, quantity, graph and kinetics choices (`compare_window.json`) (section 6.10).
- **One row per analysis**: an export's ROI file and the autosaved session with identical contents are listed once (they were shown twice, as two 'versions').
- **Versions of one `.nd2`**: every set of runs from one movie has its own colour; the new *Version* column says `newest (n of n)` / `older` / `oldest` by the saved date; the list is sorted newest first with the older analyses right under the newest one (section 6.10).
- **Kinetics**: t½ max, initial rise slope, maximum rate, time to max, amplitude and 10-90% rise time of every dish (from its mean curve, nothing fitted), with mean ± SEM / SD / 95% CI across the dishes of each group, over the same time window for every dish (default) and from the value at the baseline timepoint; shown as a dot plot in the window and saved as PNG / JPEG / SVG / TIFF / PDF, as a `.prism` with the graph made, and as CSV / Excel tables (section 6.10).
- **Carried over at the first start**: settings, the compare colours and the compare window choices from V2.5 (then older); the run indexes of V2.5, V2.4 and V2.3 are merged into V2.6's own. An existing V2.5 install of the packages is reused (the package lists are unchanged).

**V2.5.0** - changes from V2.4:

- **Background measured at every timepoint, cells included.** The background region may contain non-transfected cells (their autofluorescence is background). **Every pixel of the region is used at every timepoint** - nothing is left out; background = sum / count of all the region's raw pixels. After tracking, the background trace of each channel is checked (jump = value - running median over 5 timepoints, flagged if > 5 robust SD of the jumps **and** > 5% of the level; drift if the running median changes by > 20%; also noted when measured ROIs lie in the region); a box **Background is not steady** offers **Redraw background** (Background > Draw by hand) or **Keep it**, and the values are never changed. The automatic region is a 150 µm square (was 120 µm, cell-free) that avoids the drawn ROIs; it can be placed as a 60 µm square at a click or **drawn by hand** (freehand, Compartment *Background* > Draw by hand). Very bright objects only steer where the automatic square goes. Sessions tracked with the earlier V2.5 per-timepoint exclusion method keep their values, and their methods text describes that method (section 8.4).
- **Measurement made checkable**: ROI mean = sum of the pixel values / pixel count (as before, now computed that way and recorded); new workbook sheets `Sum_<channel>`, `Area_px`, `Area_um2` (with the background sum and pixels used), so Raw = Sum / Area_px can be verified (section 9.2).
- **Tracking rules locked to the ONLY outline**: every rule follows the cell on channel A exactly as ONLY does; WITH and AND only trim the measured pixels inside that outline, IF only gates cells - no ROI is ever bigger than its ONLY outline (V2.4's WITH outlined on the combined image) (section 6.3).
- **Hard size limits**: the followed region never has more than (1 + tol) or fewer than (1 - tol) x the drawn pixel count (brightest connected pixels kept / brightest neighbours added); *Size may change by* now goes down to **0% = exactly the drawn pixel count** at every timepoint. **No two cells' ROIs overlap** in any timepoint (sections 6.5, 8.5).
- **Tracker boundary** (step 3): per cell, lines fixed in the image that its ROIs never cross; saved with the session and listed in the methods (section 6.5).
- **AUTO-DETECT brightness slider**: keep the N brightest of the cells found; the dimmest (mean minus background on the detection image) are removed first (section 8.3).
- **Compare / average runs** (renamed from Compare runs; now at the top of the start window): runs (dishes) in **groups**; *mean of dish means* ± SEM / SD / 95% CI with **n = dishes** (the replicate statistic), pooled cells for reference, per-dish table; alignment on exact common frame times without interpolation; saves `.prism`, PNG, JPEG, SVG, TIFF, PDF, CSV and XLSX (section 6.10, 8.8). **Colours by cell line**: 520 cell lines in 18 colour families recognised from the names (look-alike characters folded); unknown lines get a colour you pick, remembered in `compare_colours.json`. **Cell line dropdown** per run (or type a new name) when the automatic match is wrong, remembered per `.nd2` in `compare_window.json`; **sortable, movable columns** (order, widths and sort remembered); runs made from the **same `.nd2`** are marked orange in *Same .nd2 as*, and ticking two of them gives a red warning and *Save...* asks first (section 6.10).
- **Built-in Prism template look** for every `.prism` (taken from a graph styled in Prism 11: 18 pt plain texts, #28D2F0 circles 4.32 pt, 0.59 pt lines, capped error bars, dotted line at X = 0; further data sets circle / square / triangle / triangle down); titles, axes, data and n follow the run; SEM error bars, the connecting line shown and automatic axes differ from the template graph. The default graph look of the live view and PNGs changed to match. Graph-look settings still at the old defaults switch to the template once; settings the user changed are kept (section 9.4).
- **Sessions de-duplicated**: a content key (hash of the ROIs, tracking, measurements and settings) is stored in every file; an unchanged session is not saved again, and the earlier-runs list shows identical saves once (section 7).
- **Run index**: at the first start the earlier-runs lists of V2.4 and V2.3 (`%USERPROFILE%\.PD4navV2.4un_history.json`, `.PD4navV2.3\...`) are merged into V2.5's own (they are only read), so *Compare / average runs* and *Analysed before* know runs saved with older versions. Runs whose files cannot be found (for example on a drive that is not connected) are not listed.
- **Settings**: copied once from `.PD4navV2.4` (then older); a carried-over automatic-background size of exactly 120 µm becomes 150 µm. Install: the package lists are unchanged (an existing V2.3 install is reused).

**V2.4.0** - changes from V2.3:

- **The live graph look goes into the Prism files.** Error type, colours, line widths, symbols, each-cell lines, titles, axis ranges and font size chosen in the *As exported* view are written into every `.prism` (export and *Save graph...*); every field was checked by opening the files in GraphPad Prism 11. Looks Prism cannot draw (shaded band, hidden mean, dashed line at time 0, key) get the closest Prism look, with a small brown note under the graph (section 9.4). A template of your own made from a PD4nav `.prism` gets the look too; other Prism graphs keep their own look. The methods text says what the Prism graphs show.
- **Load look from a Prism file...** (the Look list's last entry): the live graph takes the look of a `.prism` you styled in Prism (section 6.9).
- **Compare runs** window (File menu, the button under the export button, and the start window): the mean ± SEM of several saved, tracked runs in one graph, one colour per run, n = each run's included cells, quantities matched by channel name; saves one `.prism` (one data set per run, legend, per-run mean / SEM / n tables), PNG / SVG with a key and a CSV, into `<results folder>\Comparisons` (section 6.10).
- **Tracking settings in the window** (step 3): *Max movement between timepoints*, *IF rule: needed signal* and *AND rule: pixel threshold* (the last two shown only while a rule uses them); before, they were only in `settings.json`. They are saved with the session. Changing any of them - and now also *Size may change by* - after tracking clears the tracking.
- **Install**: a large "PLEASE WAIT FOR INSTALLATIONS" notice and window title while installing (the window can look frozen at "Installing collected packages"); clearer messages for Python 3.15+ and 32-bit Python, a failed import check (separate from a failed download), and how to retry the exact versions after a fallback. The package lists are byte-identical to V2.3's, so an existing V2.3 install is reused without downloading. Settings are copied once from `.PD4navV2.3`.
- **Fixes**: the earlier-runs list now preselects the newest run and says when a newer run without tracking (or an older one with tracking) exists; the run index is never replaced when it exists but cannot be read, and two PD4nav windows recording at once no longer lose each other's runs; under an AND rule a timepoint with no kept pixels shows the followed outline (not the drawn one); closing the window while tracking stops the tracking and waits for it before closing the `.nd2`; the zip builder ships only files tracked by git.

**V2.3.0** - changes from V2.2:

- **Tracking rules** replace V2.2's "Follow [compartment] measure [channels]" rows: `Track [compartment] using [channel A] [ONLY / WITH / AND / IF] intensity in [channel B]`. ONLY is the V2.2 behaviour, bit-identical. The step-2 "Seen on channel" choice became the read-only "Drawn and followed on" line; *Show > Tracking image* shows WITH images.
- **Every channel is measured in every ROI, always**; every channel and every ordered channel pair is exported.
- **Changing a rule after tracking now clears the tracking** (in V2.2 changing the follow rows did not).
- QC's "at or below background" and "too dim" tests use only the channels the rule uses; new IF-gate exclusion with its reason.
- **Session memory**: automatic saving into `PD4nav_sessions`, the "This file has been analysed before" dialog, *File > Earlier analyses of this file...*, a per-computer run index with `.nd2` fingerprints, "Analysed before" in the start window, saved tracking restored on loading, and "Track now?" for files without usable tracking.
- **Provenance**: the Settings sheet now lists the parameters actually used; new Methods sheet; new export item **Methods (text file)**; tracking rules, fingerprint and version in the Prism notes; tracker constants named and recorded with every tracking. Text in ROI_info that starts with `=` is now literal text (in V2.2 it became a formula).
- **Graphs**: the trace panel's *As exported* view with Prism-like presets and a full style dialog; the exported PNGs use your look. The default PNG changed from V2.2's 8 x 5 inch graph (black cell lines, blue mean with SEM band, grid, legend) to a 6 x 4.5 inch Prism-like graph (black mean with SEM error bars); the numbers are byte-identical. **Save graph...** saves the current graph as `.prism`, PNG (300 dpi) or SVG.
- **Prism template fix**: **V2.2 `.prism` graphs drew SD error bars while labelled mean ± SEM.** The bundled template now draws SEM (verified in Prism 11). The tables in V2.2 files (mean, SEM, n; each cell) were correct; only the graph's error bars were affected - re-export V2.2 analyses (load the ROI file, export) or switch the error bars to SEM in Prism.
- **Install**: exact versions for all 45 packages with a compatible fallback and `installed_versions.txt`; Python 3.11 - 3.14 preferred (3.10 gets compatible versions; 3.9 no longer accepted); a long-install-path check; `PD4NAV_INSTALL_ONLY`. **Windows only** (no Mac / Linux launcher).
- Exports work with paths longer than 260 characters.
- Settings live in `%USERPROFILE%\.PD4navV2.3` (copied once from V2.2).
- ROI files are closed right after reading (no Windows file locks).
- Unused legacy modules of the old automatic pipeline were removed.

Earlier versions, as far as they matter for opening their files:

- **V2.4** - the live graph look in the `.prism` files, Compare runs, tracking settings in step 3; ROI and session files open in V2.5 with their tracking and their pre-V2.5 background values.
- **V2.3** - tracking rules (ONLY / WITH / AND / IF), session memory and the run index, methods text; ROI and session files open in V2.4 and V2.5 unchanged.
- **V2.2** - the tracking (every ROI at every timepoint and all measurements) is saved in ROI files.
- **V2.1** - "Follow [compartment] - measure [channels]" rows; ROI files without tracking.
- **V2.0** - ROIs are made by clicking (the click-to-draw workflow).
- **V1.9** - ROI files keep the session state (choices, include / exclude).
- **V1.x** - the earlier automatic nucleus / cytoplasm pipeline; ROI files hold ROIs only.

## 16. File and code map

```
PeterPiperV1.2\
    PeterPiperV1.2.bat         launcher / installer (Windows batch)
    READ ME.txt                quick start
    README.html, README.md     this manual
    CHANGELOG.md, CITATION.cff, LICENSE, CONTRIBUTING.md
    docs\PUBLISHING.md         putting PeterPiper on GitHub, releases, DOI (V3.0)
    .github\ISSUE_TEMPLATE\    bug report / feature request forms (V3.0)
    build\                     build_zip.py (the zip), md2html.py (this manual),
                               set_github.py (the project address and DOI, V3.0)
    dev_tests\                 every validation test; run_tests.py runs them all (V3.0)
        synthmovie.py, data\synthetic_movie.npz   the shipped synthetic test movie (V3.0)
        labdata.py             'SKIPPED - lab data only' without the lab's movies (V3.0)
    app\
        PeterPiper.py        start file (adds app\ to the path, runs peterpiper.app.main)
        requirements.txt       exact package versions (45)
        requirements-compatible.txt   fallback version ranges
        install_progress.py    1.2: the launcher's 'still working' lines while pip installs,
                               the package check one by one (standard library only)
        README.md, SECURITY.md
        peterpiper\
            __init__.py        version (1.2.1), APP_NAME, PROJECT_URL / PROJECT_DOI
            app.py             start: start screen (or a queued / chosen run directly), then the
                               analysis window; error dialog hook
            config.py          Experiment and Settings (every setting and default); settings.json
            nd2io.py           reading .nd2 (Z max projection, metadata); raw TIFF and viewing-copy export
            manual.py          drawing at a click, AUTO-DETECT, resize / split / add to cell,
                               linking ROIs into cells, background (auto_background,
                               BackgroundMeter, background_warning), the tracker (track_cells,
                               hard size limits, no overlaps, boundary lines, track_params
                               and the named tracker and background constants)
            rules.py           tracking rules: TrackRule (main + helper channels, V3.0;
                               the older ONLY / WITH / AND / IF), frozen normalisation, guide
                               and helper images, the 1 um helper guard, AND overlap, WITH
                               mask, IF gate
            detectors.py       trained auto-detect: candidates, features, the learned rule,
                               held-out score, quiz, saved detectors (V3.0)
            compartments.py    whole-cell finding from a channel; robust noise
            segment.py         Roi (mask in a box), block averaging / small-piece removal
            measure.py         Measurements (means, sums, areas, background): background
                               subtraction, ratios, F/F0, R/R0
            qc.py              quality-control notes and the IF-gate reason
            graphstyle.py      graph look, presets, the statistics (mean, SD, SEM, 95% CI);
                               what a .prism can show (PRISM_SUPPORT, prism_look)
            export.py          the export list and the export itself; 1.2: the chosen folder,
                               shorter names, the paths planned before writing
            exportpaths.py     1.2: how long an export's paths will be (Excel 218, Explorer
                               259) and shorter names that fit (pure functions)
            roimerge.py        1.2: Merge - two ROIs (and their cells) joined into one
            excel.py           the workbook (formulas, Include, Graphs, Sum / Area sheets,
                               Settings, Methods)
            plots.py           graph data per quantity, drift slopes, Prism export, ROI pictures
            prism.py           .pzfx writer
            prismfile.py       .prism writer (from the template; the Compare runs .prism)
            prismstyle.py      the look inside a .prism graph (checked in Prism 11) and
                               reading a look back from a .prism (Load look from a Prism file)
            compare.py         Compare / average runs: runs, matched quantities, groups
                               (GroupLine, align, group_line), statistics, outputs
            celllines.py       cell-line recognition from names, colour families and shades
            kinetics.py        t½ max, initial rise slope ... per dish and group (V2.6)
            xyplot.py          plot builder: measures, Y vs X (trajectory / each cell), hover help (V2.7, V2.8)
            prismtemplate.py   your Prism style templates (V2.7)
            presets.py         saved analysis / plot settings (V2.7)
            outlog.py          the log of every file saved (V2.8)
            users.py           user profiles: own folder (version-free), results, whose
                               run, rename / remove (V3.0); 1.1: merge profiles, aliases,
                               roles, optional salted password hashes
            profilesync.py     1.1: keep a profile in step through a folder
            labshare.py        1.1: the lab folder - lab user list, profiles, data folders
            userprefs.py       1.1: the small per-user JSON files (storage, queue, ...)
            batchqueue.py      1.1: the movie queue
            smartselect.py     1.1: Smart auto-select - bins, unlocking, learning
            events.py          1.1: in-process events (window -> optional parts)
            achievements.py    1.1: which optional hidden extras a user has found
            cloud.py           1.1: cloud / network folders, online-only files, back-ups
            updater.py         1.1: Check for updates (the only network use, on request)
            absorb.py          1.2: finding and taking in older PeterPiper versions (carry-over,
                               shortcuts, Recycle Bin)
            syscheck.py        computer check: long-path setting, Python (V2.9); 1.2: turning
                               long paths on (Windows' administrator approval)
            templates\PeterPiper_timecourse.prism   the built-in Prism graph template
            templates\PeterPiper_look.json          the template's look per data set
            provenance.py      software versions, parameter table, methods text, references
            roifile.py         ROI and session files (.npz), summaries, tracking checks,
                               content_key
            history.py         fingerprints, earlier-runs search, run index, dedupe_runs
            safety.py          safe file names, never-overwrite and atomic own-file writes
            gui\
                setup.py       start screen (1.1; 1.2: offers to absorb older versions)
                absorbdlg.py   1.2: 'Older PeterPiper versions are on this computer'
                theme.py       themes and their WCAG contrast check (V2.9, 1.1)
                colourvision.py 1.1: contrast, colour-vision simulation, CIEDE2000
                storagedlg.py  1.1: 'Storage & cloud' and 'Back up this analysis'
                updatedlg.py   1.1: 'Check for updates'
                charlotte.py, charlotte_draw.py, charlotte_themes.py, charlotte_words.py
                               1.1: Charlotte's Web (never touches data)
                eggsdlg.py     1.1: Help > Achievements
                traindlg.py    'Train auto-detect' window (V3.0)
                userdlg.py     'Who is using PeterPiper?', merge, keep in step, lab
                               settings, passwords (V2.9, 1.1)
                syscheckdlg.py 'Computer check' window (V2.9; 1.2: Turn on Windows long paths)
                clickwin.py    analysis window: step pages 1-5, tools (1.2: Merge), AUTO-DETECT
                               slider and Smart auto-select button, background (click /
                               freehand), Tracker boundary, tracking, SAVE, the queue row,
                               autosave, help; 1.2: the long-path warning of an export
                traces.py      trace panel: include / exclude, Check cells / As exported, styles,
                               the brown Prism note, Load look from a Prism file
                comparewin.py  Compare / average runs window (groups, colours by cell line;
                               1.1: menus, Save / User columns, Open in analysis, Output files;
                               1.2: Close)
                measurerow.py  the plot builder's sentence of dropdowns (V2.7, V2.8)
                templatedlg.py Prism style templates dialog (V2.7)
                batchdlg.py    batch analysis of .nd2 files (V2.7; 1.2: Save exports in)
                outlogdlg.py   'Saved files...': every save, click to open (V2.8)
                exportdlg.py   export list dialog (1.2: Save in)
                historydlg.py  earlier analyses dialog
                imageview.py   image canvas and brightness bar; freehand (lasso) and
                               polyline drawing; boundary lines and left-out background pixels
                frames.py      background frame reading and cache (current frame first, V3.0); display copy (V2.9)
                widgets.py, workers.py   small widgets (fading notes, step pages, the
                               cell colours and line styles, 1.1; 1.2: the loading bars -
                               BusyPanel, ProgressStrip, TimeLeft, run_with_progress, busy);
                               background jobs
```

`app\README.md` has a shorter code map; `app\SECURITY.md` the security notes.

## 17. License

PeterPiper is released under the **MIT License** - Copyright (c) 2026 Peter DePaola IV (Schmitt Lab, UCLA). You may use, copy, modify, merge, publish, distribute, sublicense and sell copies, provided the copyright and permission notice are included; the software is provided "as is", without warranty of any kind. The full text is in `LICENSE`.

The packages PeterPiper installs are not part of PeterPiper and keep their own open-source licences (see each package's metadata in the private environment; Qt for Python / PySide6 is used under the LGPL-3.0). GraphPad Prism is commercial software and is not part of PeterPiper.
