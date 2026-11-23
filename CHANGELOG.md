# Changelog

## PeterPiper 4.0.0 (2026-11-22)

The measurements are unchanged: the same inputs give the same numbers (a full tracking
is bit-for-bit the same as in 1.2). Saved runs, ROI files and sessions of every earlier
version open in 4.0.

1. **One download for Windows and macOS.** The same folder runs on both
   (`PeterPiperV4.0.bat` / `PeterPiperV4.0.command`); the system is detected when the
   program starts.
2. **Re-track single cells.** After tracking, a change to one cell (moved, redrawn,
   added or removed, its boundary line, the background) re-tracks only what it
   affects, by itself, a moment after your last change - the result is exactly what
   a full track gives. Cells being updated are drawn grey and dashed. Tracking itself
   is about 10x faster when the frames are in memory (several processes).
3. **Undo and Back everywhere.** Undo (top row, beside the cell list, Ctrl+Z) takes
   back adding, removing, moving and changing ROIs, include / exclude, the compartment
   you chose and the background chosen. Every page has **Back**.
4. **A graph builder.** "Y vs X (vs Z)" of any per-cell quantity, typed like a sentence
   (`R/R0 nuclear Cy5/GFP vs time binned by summed DAPI at T=0`) or picked from three
   rows; binned or coloured; per run and, in Compare, across runs (each run's mean and
   SD band by default). T=0 is the baseline.
5. **Long jobs in the background.** Exports, viewing copies and raw TIFFs, autosaves,
   copies and uploads run in the background with their own progress (the task button,
   bottom right: time left, Cancel, Retry, Open folder). **Next movie never waits for
   them.** Quitting while they run asks whether to wait, cancel them or quit anyway;
   an export that was cut off is clearly marked.
6. **Backup and the lab folder on the start page** only (no longer in the analysis
   window). The baseline drift slope is an optional **add-on**: it is written only
   when you tick it.
7. **Working from the lab folder** is not slow: a movie there is copied to a local
   cache first (with a bar; the next movie of the queue is fetched ahead), results
   are uploaded safely in the background, and an in-app guide explains how the lab
   folder works.
8. **The background first.** PeterPiper proposes empty, dark places, each with its
   mean per channel; browse them and press +, or draw your own. Every ROI then shows
   its **N x background** (ROI mean / background mean, per channel, at the timepoint
   shown) - always, also zoomed out (then the number only); hover for the exact
   intensities; outlines can be coloured by level.
9. Developer settings are no longer reachable from the normal menus.
10. **The baseline timepoint** is chosen right beside the cell include / exclude list,
    and the graph always fits itself to what it shows.
11. **A clean four-page flow**: Start (queue, lab folder, backup) > Draw (background
    first, then the cells) > Track & check > Graphs & export. One page at a time,
    one line saying what to do now, one status line, every control explained on
    hover, no scroll bars on a 1366 x 768 screen.
12. **ROI troubleshooter**: for one problem cell, PeterPiper tries the sensible other
    tracking rules and settings side by side; you pick the best by eye and only that
    cell is tracked again.

New developer tests: `test_v40_flow.py`, `test_v40_safety.py`, `test_v40_view.py`,
`test_v40_server.py`, `test_v40_trackx.py`, `test_v40_graphs.py`, `test_v40_launch.py`,
`test_v40_speed.py`.

## PeterPiper 1.2.2 (2026-11-17)

The methods and the numbers are unchanged; the same program folder as 1.2.0, so
*Check for updates* updates 1.2.0 / 1.2.1 in place.

- **Also keep a copy in** (*Storage & cloud*): a second results folder - e.g. the
  cloud and your own drive. Every autosave, SAVE and export is copied there in the
  background (`cloud.keep_copy`); only results, never the movie; PeterPiper's own
  earlier copy is updated, anything else of the same name is kept (`_2`).
- **Saved files** lists every analysis (SAVE logged; the run list shown even when the
  log is empty); its buttons are greyed out when there is nothing to open, and *Open
  file* opens the picked save's first file.
- The start screen's *Storage & cloud* button no longer reads "Storage _cloud".
- New developer test `dev_tests/test_v122_storage.py`.

## PeterPiper 1.2.1 (2026-11-16)

**A correction to *Keep in step*.** The methods and the numbers are unchanged; the same
program folder as 1.2.0, so *Check for updates* updates 1.2.0 in place.

- *Keep in step* refuses the lab folder, or a folder inside it, as a person's own
  folder (`profilesync.lab_conflict`): the lab folder already keeps every profile in
  step in `PeterPiper profiles`, so choosing it made a second copy in the lab's shared
  folder. The window says when the lab folder covers the profile; an older setting
  that points into the lab folder is no longer used (the note says so), and the lab
  folder's copy carries on.
- New developer test `dev_tests/test_v121_sync.py`.

## PeterPiper 1.2.0 (2026-11-16)

**Merge for ROIs, a choice of export folder with help for paths too long for
Windows, loading bars with the percent and the time left, a launcher that reuses an
identical earlier install, and taking in older PeterPiper versions.** The methods
and the numbers are unchanged (the same measurement code; every earlier test suite
that could run passes - README section 12); the only new editing step is the Merge tool.

- Program folder and launcher `PeterPiperV1.2` / `PeterPiperV1.2.bat`, install folder
  `%USERPROFILE%\.PeterPiperV1.2`; the same package versions as 1.0 and 1.1; users
  and runs in `PeterPiper data` carry over. Mac: `PeterPiper-1.2.0-macOS-AppleChip.dmg`
  / `-Intel.dmg`.
- **Merge** (analysis window, step 2; the tool buttons are now two rows: Add, Remove,
  Draw by hand, Resize / Split, Merge, Add to cell): click an ROI, then the one next
  to it that belongs to the same cell; they become one ROI with the first one's
  number. The gap is filled by the smallest closing (radius 1, 2, 3 ... px) that
  makes them one 4-connected piece, kept only between them and never on another
  cell's pixels; holes the join closes in are filled. Refused beyond 3 µm ("These
  two ROIs are not next to each other") or when another cell lies between them.
  Compartments both cells have are merged the same way (or the merge is refused,
  naming the compartment); one only the second cell has comes along. Tracking is
  cleared, Undo restores both, a merge is not counted as a hand-drawn ROI
  (`roimerge.merge_rois`, `merge_cells`). The Methods text says ROIs "could be
  resized, split, merged, extended or drawn by hand".
- **Export folder**: the export list has *Save in:* with *Change...* and *Usual
  folder*; the export goes to `<chosen folder>/Export_<date>_<time>`, an unwritable
  folder is refused, autosaves and SAVE stay in the results folder, and the choice is
  kept for the movie's next export. Batch analysis: *Save exports in* (one subfolder
  per movie, `<chosen>/<movie name>/Export_...`; the batch log goes there too).
- **Long paths**: with Windows' long paths off, an export whose paths would be too
  long (Excel does not open a workbook whose path is over 218 characters; Explorer
  has trouble over 259) offers *Shorten names for me* (default; shows the new name
  and the longest path first; cuts the middle of the name, then may use the short
  folder name `Export_yymmdd-hhmm`), *Show Details...*, *Choose another folder...*,
  *Turn on Windows long paths* (Windows' own administrator approval, then checked
  again), *Export anyway* and *Cancel* (`exportpaths.py`). Batch runs shorten by
  themselves and say so in the log. Graph titles keep the full name. *Help >
  Computer check* has the same *Turn on Windows long paths* button.
- **Loading bars**: every working window and the analysis window's progress strip
  show a bar with the percent (or a moving bar when the amount is unknown), "about 1
  min 20 s left" / "estimating time left..." / "almost done" (or "12 s so far"), what
  is happening and a detail line naming the file, folder or count (shortened in the
  middle; the whole text on hover); a finished strip says "took ...". Folder
  searches give a real fraction; saving and exporting name each file; reading a saved
  run, the recent analyses, adding several runs in Compare and a batch folder have
  bars too. Window titles are never empty (a drive root such as `D:\` is named in
  full).
- **Launcher**: reuses an identical earlier install (`.PeterPiperV1.1`, then
  `.PeterPiperV1.0`, then PD4nav's), so 1.2 opens at once on a computer with 1.1.
  While installing, `app/install_progress.py` (standard library only) passes pip's
  output through and, whenever pip is quiet for 5 s, prints a "still working - ..."
  line (package looked up / downloading <name> (<size>) - n of 45 / installing ...,
  with the time so far and about how long is left); step [3/3] checks each package
  one by one ("checking numpy ... OK (1 of 14)"); step [1/3] says it takes about
  10-30 s; each start says "Starting PeterPiper - the window opens in about 10-20
  seconds." after an install, else "... in a few seconds.". pip's own bars now appear
  when each download is finished, not live. A real install took 132 s.
- **Taking in older versions** (start screen, once per start; `absorb.py`,
  `gui/absorbdlg.py`): older PeterPiper versions (1.0 and later, never PD4nav),
  found through `%USERPROFILE%\.PeterPiperVx.y` folders, `shortcuts_for.txt`, the
  `PeterPiper.lnk` shortcuts (Desktop, Start menu, program folder) and
  `PeterPiperVx.y` folders next to this one, are listed with their program folder,
  private Python and sizes: *Absorb* / *Not now* / *Don't ask again for these*
  (remembered in `PeterPiper data/absorb.json`). Absorb copies what the old version
  kept for itself into `PeterPiper data` (error logs and `installed_versions.txt` to
  `logs/PeterPiperVx.y`; settings files to the user or `carried over/`; run lists
  merged; nothing overwritten), points the Desktop and Start-menu shortcuts at this
  version, then moves its recognised program files and its private Python to the
  Recycle Bin (restorable; Mac: Trash). Never touched: the user's own files in the old
  folder (listed), a developer copy (`.git`), the private Python this version uses,
  the running program, `PeterPiper data`. An open version is left alone ("close it,
  then try again"); drives without a Recycle Bin are refused; with a newer version
  present nothing is offered. `PETERPIPER_NO_ABSORB=1` turns it off.
- **Compare window**: a *Close* button at the bottom right (the same as the window's
  X).
- Manual: new section 3.8; sections 3, 6.0, 6.2, 6.4, 6.7, 6.10, 6.12, 8.2, 8.12,
  9.1, 12 - 16 updated.

## PeterPiper 1.1.0 (2026-11-15)

**A new start screen and analysis window, the movie queue with SAVE, Smart
auto-select, profiles shared between computers and across a lab, storage in cloud
folders, colour-blind-safe colours and Check for updates.** The methods and the
numbers are unchanged (the same measurement code; every earlier test suite passes).

- Program folder and launcher `PeterPiperV1.1` / `PeterPiperV1.1.bat`, install folder
  `%USERPROFILE%\.PeterPiperV1.1` (one install of about 5 minutes per computer; the
  same package versions as 1.0); users and runs in `PeterPiper data` carry over.
  Mac: `PeterPiper-1.1.0-macOS-AppleChip.dmg` / `-Intel.dmg`.
- **Start screen** (opens maximized, no scroll bars at 1366 x 768): *Analyse movies*
  (one .nd2, or several at once - a movie queue), *Continue your queue (N left)*,
  *Compare / average saved runs*; a movie card with every earlier check (pixel size,
  frame interval, uneven gaps, stage position, channel names, results folder with
  *Open results folder*, analysed before, read-only drives); tabs *Recent analyses*
  (open a run straight into the analysis window) and *Queue*; footer *Saved files*,
  *Storage & cloud*, *Check for updates*, *More* (batch, Prism templates, export /
  import profile), text size, theme; the Smart auto-select status line. A movie from
  the queue or a run list skips it only when its metadata is complete (pixel size
  present and not 1.0, interval > 0, even gaps, one stage position).
- **Analysis window**: opens maximized; one step page at a time; SAVE (with an
  optional note) and EXPORT at the foot of the panel; top row *Another file*, *Open
  results folder*, *Compare*, *Undo* and, in a queue, *Movie 2 of 5*, *Skip*, *Next
  movie*; Smart auto-select beside AUTO-DETECT; *File > Back up this analysis...*;
  *Help > Check for updates...*; *Help > Achievements...* once something is found.
- **SAVE**: a saved ROI file with the tracking (kind `saved`) and the note in its
  summary, shown in Compare as *Saved: <note>*. The autosave is unchanged.
- **Movie queue**: statuses to do / saved / exported / skipped, kept per user;
  *Next movie* asks to SAVE first if needed.
- **Compare window**: eight buttons instead of twenty (menus *Add runs*, *Groups*,
  *Output files*, *List*, *More*), opens maximized, a clearer list with the columns
  *Save* (Saved: note / Autosave / Export) and *User*; *Open in analysis* (finds the
  movie by its saved path, the run index or next to `OUTPUT_`, or asks; checks the
  fingerprint), *Open results folder*, *This run's output files*.
- **Smart auto-select**: cell selection learned from your hand-picked movies, kept
  in named bins (one per kind of experiment, same channel names, any number of ROIs);
  n = hand-picked movies on the button. The V3.0 trained auto-detect (your saved ROIs
  as answers, IoU >= 0.3; limits on fixed grids by coordinate search maximising mean
  F1; held-out score, each movie scored by the rule learned from the others), learned
  in the background on use from >= 2 movies whose files are present. The detector's
  name carries the bin, n and the ROI count into the Methods text of every run that
  used it. Unlocked by hand-drawing and SAVEing 3 movies of a queue; plain and
  trained AUTO-DETECT unchanged.
- **Profiles and lab**: a redesigned *Who is using PeterPiper?*; *Merge profiles*
  (two spellings, or a profile zip / folder from another computer, into a chosen
  user; the kept profile wins ties; run lists united; the merged user hidden, never
  deleted, its name an alias); *Keep in step* through a personal cloud or network
  folder (both ways at start, switch and close; unions, newest wins only for single
  values, conflict copies kept); a *lab folder* (`PeterPiper lab users.json`,
  `PeterPiper profiles/`) with one lab user list, aliases, profiles and the lab's
  data folders for every linked computer, and an *anyone can add themselves*
  switch; roles User / Admin / Developer (Developer = a title, Admin's abilities;
  the last admin cannot be demoted); optional passwords (salted PBKDF2-SHA256,
  200,000 iterations, 16-byte salt; admins can reset; not strong security).
- **Storage & cloud**: results next to each movie (default) or in a folder
  (`<folder>/OUTPUT_<movie>/<user>`), e.g. in OneDrive / SharePoint / Teams, Google
  Drive, Box, Dropbox, iCloud Drive, Nextcloud / ownCloud, pCloud, MEGA, Sync.com,
  Egnyte or a network drive - through the services' own apps; PeterPiper never signs
  in. *Back up this analysis* into `<folder>/PeterPiper backup/<movie>/` (results and
  optionally the .nd2; never overwrites: same size and time = skipped, else `_2`;
  sizes checked). A warning when a movie is stored only online.
- **Colours and accessibility**: cell colours #2299CC, #BB2200, #5533FF, #AA8844,
  #EE3388, #007755 in every theme (Okabe-Ito hues at medium luminance; >= 3.23:1 on
  white, >= 3.30:1 on black; every pair >= 14.4 CIEDE2000 apart with normal vision
  and simulated protanopia, deuteranopia and tritanopia); dashed / dotted / dash-dot
  beyond six cells (24 looks); a white trace plot in every theme; colour swatches in
  the cell list. Every theme checked against WCAG 2 contrast (text >= 7:1, secondary
  text, text on accent and status colours >= 4.5:1, borders >= 1.25:1); the basic
  themes adjusted slightly; 18 optional palettes as a hidden extra.
- **Check for updates** (start screen, Help menu): the only network use, only when
  pressed - one HTTPS request to GitHub's public release list and, if you choose,
  the release download. Windows: changed program files replaced in place (old ones
  kept in `_update_backup/`), or a new version unpacked into its own folder; Mac: the
  right .dmg saved in Downloads and opened; developer copies never changed; user
  data never touched.
- **Charlotte's Web**: a small game (pink button) - a unique web for every movie
  picked by hand, finished by SAVE, collected in a gallery and exportable as
  pictures; it stores only its own file and never touches data, measurements or
  results. A few further optional hidden extras.
- Manual: new sections 6.14 - 6.19 and 8.13; privacy, storage, troubleshooting,
  limitations and validation updated.

## PeterPiper 1.0.3 (2026-11-12)

**Movies on a drive PeterPiper cannot write to** (e.g. a Windows-formatted external
drive on a Mac, which macOS can read but not write).

- Before: *Start* ended in an error (`Read-only file system`), because the results
  folder next to the movie could not be made.
- Now the start window checks that the results folder can be written before anything
  starts (on every system: read-only drive, full drive, no permission), says why in
  plain words, and offers `PeterPiper results/OUTPUT_<movie>/<user>` in the home
  folder or another folder. On a Mac a read-only drive is recognised as soon as the
  movie is chosen, and that folder is suggested at once. The movie is only read.
- Batch runs: such a movie's results and the batch log go there (the log says so).
- Compare saves there instead of the home folder; earlier runs saved there are found.
- Methods and numbers unchanged.

## PeterPiper 1.0.2 (2026-11-10)

**PeterPiper for Mac.**

- `PeterPiper.app` for macOS 14 or newer, Apple-chip and Intel Macs: drag into
  Applications and double-click; it carries its own Python and the tested packages.
  Built for each release on GitHub's Mac machines (`.github/workflows/mac-app.yml`,
  `build/peterpiper_app.spec`): the developer tests run on macOS, the finished app runs
  its self-test, and the `.dmg` files are attached to the release.
- `PeterPiper --selftest [folder [movie.nd2]]` (both systems): every module and library,
  the complete .nd2 reader, then a whole analysis of a built-in synthetic movie with
  known answers and an export of every file type.
- Compare recognises the same .nd2 whatever the case and slash direction of its saved
  path, on every system.
- macOS details: files open with their Mac program, Mac fonts, the Windows-only
  long-path check is skipped, crash reports in ~/Library/Logs/PeterPiper, the Mac icon.
- On Windows nothing else changes (same launcher, same install).

## PeterPiper 1.0.1 (2026-11-10)

The program works exactly as 1.0.0 (same methods, same numbers).

- The project's Zenodo DOI (10.5281/zenodo.24120837) in `CITATION.cff`, the README and
  *About PeterPiper*.
- The manual's examples no longer name the lab's sensor.
- The developer tests no longer contain the lab's own file names and folders (they
  named unpublished experiments): tests ask `labdata.T(key)`, which reads a local list
  (`dev_tests/lab_paths.json`) that is never uploaded; without it those tests are
  skipped as before. Test logs are no longer kept in the repository.

## PeterPiper 1.0.0 (2026-11-10)

PD4nav is now **PeterPiper**. PeterPiper 1.0 continues PD4nav V3.0: the same
methods and the same numbers, with

- the new name everywhere (window titles, files PeterPiper writes, Methods text,
  manual; the program folder `PeterPiperV1.0`, the launcher `PeterPiperV1.0.bat`,
  the code package `peterpiper`);
- the logo: at the top of the start window and *Who is using PeterPiper?* (black on
  the light theme, white on the dark), as the window and taskbar icon, and drawn
  in block characters in the launcher's window at the first install and at every
  start (the widest of 116 / 100 / 72 characters that fits);
- *PeterPiper* shortcuts with the logo icon (next to the `.bat`, on the Desktop
  and in the Start menu), made by the launcher the first time and again if the
  folder moves (`PETERPIPER_NO_SHORTCUTS=1` turns this off);
- a fresh start on every computer: users, settings and run lists live in
  `%USERPROFILE%\PeterPiper data` and nothing is taken over from PD4nav (whose
  data is left untouched; a PD4nav profile can be imported on purpose);
- files PeterPiper writes name the app (`app`), so earlier-analysis lists and
  Compare show "PeterPiper 1.0" or "PD4nav 3.0"; PD4nav's ROI / session files,
  `PD4nav_sessions` folders, saved settings and trained auto-detect files are
  still read; new sessions go to `PeterPiper_sessions`;
- `build/make_logo_assets.py` makes the icon, the logo pictures and the terminal
  art from the logo picture.

The repository was started fresh for PeterPiper; PD4nav's full history (V2.2 -
V3.0, every commit) is below and in the PD4nav repository.

---

# PD4nav changelog (before the new name)

Every PD4nav version, newest first (the same text as section 15 of the manual, `README.md`), followed by the complete edit log: every commit in this repository, oldest first. Earlier history (V1.5 - V2.1) is summarised in the version history; those versions were developed before this repository was started at V2.2.

## Version history

**V3.0.0** (this version) - changes from V2.9:

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
- **Run index**: at the first start the earlier-runs lists of V2.4 and V2.3 (`%USERPROFILE%\.PD4navV2.4
un_history.json`, `.PD4navV2.3\...`) are merged into V2.5's own (they are only read), so *Compare / average runs* and *Analysed before* know runs saved with older versions. Runs whose files cannot be found (for example on a drive that is not connected) are not listed.
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

## Edit log (every commit)

| Date | Commit | Change |
|---|---|---|
| 2026-10-29 | `50b2197` | V2.2 baseline |
| 2026-10-29 | `8e31298` | V2.3 baseline: version strings, LF endings, new Settings fields |
| 2026-10-29 | `2fe6887` | rules: ignore _home |
| 2026-10-29 | `27f8c26` | graphstyle: GraphStyle, presets, stats, matplotlib renderer, PRISM_SUPPORT |
| 2026-10-29 | `8c16f14` | rules: tracking rules module, track_cells rules/params/gate, named tracker constants |
| 2026-10-29 | `39d29e1` | history: session memory backend (roifile summary/session file, history index + scan) |
| 2026-10-29 | `0f26113` | rules: qc rule channels, IF gate reason, quiet NaN warnings; synthetic unit test |
| 2026-10-29 | `1394947` | provenance: methods text, parameter table, Methods sheet, Prism note (WIP) |
| 2026-10-30 | `a785f4d` | graph: WIP checkpoint (session limit interruption) |
| 2026-10-30 | `121ac6d` | pack: WIP checkpoint (session limit interruption) |
| 2026-10-30 | `9396ea8` | history: WIP checkpoint (session limit interruption) |
| 2026-10-30 | `e6de2c8` | rules: WIP checkpoint (session limit interruption) |
| 2026-10-30 | `b093127` | restore READ ME line endings |
| 2026-10-30 | `f4a60e3` | history: fix safety.py escape regression, faster session-file compression, clearer no-tracking reason |
| 2026-10-30 | `404d9c2` | traces: header no longer keeps a stale second line after As exported; test compares common area |
| 2026-10-30 | `9bbb352` | pack: build_zip.py, README/SECURITY for V2.3, Windows-only requirement headers, READ ME install text |
| 2026-10-30 | `a422ccd` | provenance: developer test (Settings refs, Methods, literal text, V2.2 side-by-side, pzfx, real data) |
| 2026-10-30 | `1d3fcff` | dev_tests: graph test on real tracked measurements (CSV = V2.2, panel PNG = export PNG) |
| 2026-10-30 | `0497499` | rules: real-data test finished (WITH plane check, AND discard/empty path, k sweep); tidy manual.py line; norm docstring |
| 2026-10-30 | `88c4fc1` | pack: long-install-path check in the launcher, Windows-only requirements header, bat test runs 5-6 and --home |
| 2026-10-30 | `c038a4b` | pack: test logs (pip wheel matrix, real .bat install, zip build) |
| 2026-10-30 | `3156477` | merge history |
| 2026-10-30 | `be395f4` | merge graph |
| 2026-10-30 | `1cf23fa` | merge provenance |
| 2026-10-30 | `79cc6c6` | merge pack |
| 2026-10-30 | `3547166` | Prism template: error bars show SEM (byte 12 of the bound 8028 plot: 1=SD -> 2=SEM), verified in Prism 11 |
| 2026-10-30 | `f10346b` | int pass A: tracking rules in the window, all channels always, export provenance + Methods text |
| 2026-10-30 | `0adaf73` | int pass B: session memory - earlier runs offered, tracking restored, autosave |
| 2026-10-30 | `eba9c19` | docs: in-depth manual (README.md + README.html), md2html builder, V2.3 quick start |
| 2026-10-30 | `8e139f4` | int pass C: live graph wired into the window, long Windows paths, clean-up |
| 2026-10-30 | `18de122` | build_zip: leave out _out (test output folder, git-ignored) like _home and _work |
| 2026-10-30 | `553ddb0` | merge docs (README.md, README.html, READ ME.txt) |
| 2026-10-31 | `db2f895` | review: session file kept after loading a run, IF exclusions follow the rule, other-movie tracking not reused, launcher error log |
| 2026-10-31 | `b75c9c6` | launcher: findstr for long-path check, clear PYTHONHOME/PYTHONPATH; methods text: PNG vs Prism error bars; requirements note on 3.14.1 |
| 2026-10-31 | `9095c91` | V2.4 launcher: PLEASE WAIT FOR INSTALLATIONS notice, title during install, reminder before the silent pip step |
| 2026-10-31 | `555a9ef` | V2.4 plan |
| 2026-10-31 | `04f2d98` | V2.4: version 2.4.0, PD4navV2.4.bat (reuses a V2.3 venv with identical requirements), settings carried over from .PD4navV2.3 |
| 2026-10-31 | `fe1fd4a` | Prism: live graph look in every .prism (prismstyle merged from prism_style_dev), closest Prism look for band / hidden mean / dashed line with plain warnings, methods text says what the Prism graphs show |
| 2026-10-31 | `2cae5a0` | dev test: live graph look -> .prism, checked in Prism 11 |
| 2026-10-31 | `b5c1d23` | dev tests: Prism SVG resolution tolerance, UTF-8 output |
| 2026-10-31 | `1e94fd3` | launcher test logs regenerated for PD4navV2.4 |
| 2026-10-31 | `f208a2c` | Load look from a Prism file: prismstyle.read_style + trace panel / More style buttons |
| 2026-10-31 | `d4cf91e` | Compare runs core: compare.py, prismfile.write_compare_prism, prismstyle.add_dataset_plots (one coloured plot per run, legend; checked in Prism 11) |
| 2026-10-31 | `b8c5506` | Compare runs window (gui/comparewin.py), opened from File menu, the button under export and the start window |
| 2026-10-31 | `804056a` | dev test: Load look from Prism + Compare runs (42 checks, Prism 11 session) |
| 2026-10-31 | `a7f4b0c` | read_style: plain message without the technical detail |
| 2026-10-31 | `eb19a27` | Load look from a Prism file: as the Look list's last entry (no new widget: the Check cells view keeps its exact layout); test |
| 2026-10-31 | `6355598` | Tracking settings in step 3 (max movement, IF signal, AND threshold; IF/AND shown when a rule uses them); any change clears tracking (L8); saved in session state; launcher messages (L3) |
| 2026-10-31 | `ef9eecb` | Run index: unreadable index never overwritten, lock + re-read/merge for two processes (L4); tests |
| 2026-10-31 | `0a540a0` | Earlier-runs dialog: newest run preselected, newer/older run notes (L5); AND empty frame shows followed outline (L7); tests |
| 2026-10-31 | `d652c5f` | Closing while a job runs: cancel and wait for the worker before closing the .nd2 (L11); test |
| 2026-10-31 | `804965b` | build_zip: only git-tracked files ship, untracked strays skipped and listed (L10); release/ ignored; test |
| 2026-10-31 | `a7383bc` | Docs for V2.4: README (Prism look, closest-look table, Load look, Compare runs, step 3 settings, install, history, code map), READ ME.txt, app/README.md, plan done |
| 2026-10-31 | `aa6b9c6` | test_pack_bat: fix line split in the L3 check |
| 2026-10-31 | `5019ffd` | README: V2.4 validation counts; README.html rebuilt |
| 2026-11-02 | `14c5afe` | Start V2.5 from V2.4: version 2.5.0, launcher renamed, plan |
| 2026-11-02 | `2d0281b` | WIP checkpoint: V2.5 chunks A and B (interrupted) |
| 2026-11-02 | `6503770` | V2.5 chunk A: background incl. cells, rule lock, 0% size, boundaries, detect slider, session de-dup, sum/area sheets (chunk B WIP included) |
| 2026-11-02 | `448d0af` | V2.5: integration fixes, tests updated for intended changes, README/quick start, old graph look migration |
| 2026-11-02 | `59cca3b` | V2.5: merge the V2.4/V2.3 run indexes into V2.5's at first start |
| 2026-11-02 | `1c0be5c` | V2.5: background uses every pixel with a fluctuation check and redraw prompt; compare window cell-line dropdown, sortable/movable columns, same-.nd2 warning |
| 2026-11-02 | `0b6ac49` | V2.5 docs: all-pixel background with fluctuation check; compare dropdown, sorting, same-.nd2 warning |
| 2026-11-02 | `53707e2` | V2.6: compare remembers groups, versions of one .nd2, response kinetics |
| 2026-11-02 | `b86e948` | V2.6 fixes from testing on real runs: one row per analysis, kinetics window and baseline |
| 2026-11-02 | `a6a406d` | V2.7: version 2.7; background warns only for an object in the region or >5% cell overlap |
| 2026-11-02 | `961858c` | V2.7: Compare plot builder - Y measure vs time or vs another measure (trajectory / each cell), right Y axis |
| 2026-11-02 | `f6bc573` | V2.7: every XY table in a .prism gets its own graph (cloned the way Prism's DuplicateFamily does); automatic tick interval on automatic axes |
| 2026-11-02 | `a6c142f` | V2.7: Prism style templates (your XY and column graph look, remembered), saved analysis / plot settings, batch analysis and batch plot saving |
| 2026-11-02 | `477ff61` | V2.7 docs: manual sections 6.10-6.12, 8.4, 9.4, validation, version history, MIT license, CITATION.cff |
| 2026-11-02 | `d990d4b` | CHANGELOG.md: every version and every commit |
| 2026-11-03 | `041196d` | V2.8: every measure (raw, background, dF/F0, dR/R0, sum, area, compartment ratios) vs any; run tree with movie folders; groups panel; graph toggles, each cell, hover, legend hide; explanations on hover |
| 2026-11-03 | `25cb139` | V2.8: run list in folders by group (drag runs onto a group), Version = PD4nav version, SD by default, saved-files log, Save options in the Save dialog, resizable dividers, trajectory start/end markers, dot-plot mean cross, real axis values |
| 2026-11-03 | `5fef0c7` | V2.8: Save asks about a movie counted twice before the file types; docs and validation; tests for the group folders |
| 2026-11-03 | `3a96ae9` | CHANGELOG.md: V2.8 and every commit |
| 2026-11-03 | `e91aaab` | V2.9: Midnight / Daylight themes, Learn from my runs (AUTO-DETECT limits and keep / remove suggestions, used only when chosen), step bar with folding steps, fading notes, smoother playback; docs and validation |
| 2026-11-03 | `9774a04` | CHANGELOG.md: V2.9 and every commit |
| 2026-11-07 | `75e2d5d` | V2.9 polish: user profiles (own folder, own results, own runs listed), loading bars for slow work, faster Compare window, Compare baseline line at time 0, first-start computer check (long paths, Python); docs and validation |
| 2026-11-07 | `dbabd30` | CHANGELOG.md: V2.9 polish |
| 2026-11-08 | `f70e878` | V2.9 recommendations round: ratio check, SD default, no auto background, portable profiles, GitHub prep |
| 2026-11-08 | `276d73e` | V2.9 changelog |
| 2026-11-08 | `991bd52` | PD4nav V3.0: this round's changes released as version 3.0.0 |
| 2026-11-08 | `efb4ca0` | V3.0 changelog |
| 2026-11-09 | `57a3a8f` | V3.0: helper channels replace ONLY/WITH/AND/IF (older rules applied exactly); Train auto-detect from my runs |
