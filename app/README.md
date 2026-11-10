# PeterPiperV1.0

Click-to-draw (plus 'auto-select the obvious ones') ROI tracking for Nikon .nd2
fluorescence time series. See `READ ME.txt` next to `PeterPiperV1.0.bat` for how to use it.

Install: `PeterPiperV1.0.bat` makes a private Python environment in
`%USERPROFILE%\.PD4navV3.0\venv` from the exact versions in `requirements.txt`
(fallback: `requirements-compatible.txt`); what was really installed is written to
`venv\installed_versions.txt`. After that everything runs locally (see `SECURITY.md`).

Code map (`peterpiper/`):
- `manual.py` - drawing an ROI at a click, auto-select, linking ROIs into cells,
  background, and the tracker (every ROI redrawn at every timepoint)
- `history.py` - remembers earlier runs of an .nd2 file (next to the data and in a
  per-computer index) so they can be loaded again
- `roifile.py` - saving / loading the ROI file and the session file (with the tracking)
- `provenance.py` - the settings and versions behind every number (for methods sections)
- `graphstyle.py` - how the graph looks (mean, error bars, symbols, titles, axes):
  the one place the mean / SEM / SD / 95% CI are computed
- `gui/clickwin.py` - the main window; `gui/setup.py` - the start window
- `gui/frames.py` - frames read in the background (smooth scrubbing / Play; V2.9: a
  half-size display copy of big frames, display only; V3.0: the frame you are on is
  read first, frames passed over are skipped, closing waits for a read in progress)
- `gui/theme.py` - the Midnight (dark) / Daylight (light) look of every window (V2.9)
- `users.py`, `gui/userdlg.py` - user profiles: each user's own folder (%USERPROFILE%\PeterPiper
  data, the same for every version) and results, only their own runs listed; rename / remove,
  export / import, runs found again on another computer (V2.9; the shared folder and
  portability V3.0)
- `syscheck.py`, `gui/syscheckdlg.py` - the computer check (long-path setting, Python) (V2.9)
- `gui/traces.py` - the trace panel (include / exclude, zoom, hover readout) and the
  live graph ('As exported' view: the look of the PNG graphs, 'Save this graph...')
- `gui/exportdlg.py`, `export.py` - the export list and the export itself, and the
  'Save this graph' dialog
- `gui/historydlg.py` - the 'analysed before' list of earlier runs
- `gui/imageview.py`, `gui/widgets.py`, `gui/workers.py` - the image, small controls
  (and the cell colours), background jobs
- `excel.py`, `plots.py`, `prism.py`, `prismfile.py` - Excel, PNG and Prism output (a
  .prism file is made from the Prism template with the data, titles and the live look)
- `prismstyle.py` - the look inside a .prism graph (error type, colours, lines, symbols,
  axes, fonts; every field checked in Prism 11) and reading a look back from a .prism
  ('Load look from a Prism file')
- `compare.py`, `gui/comparewin.py` - 'Compare runs': the mean of several saved, tracked
  runs in one graph (.prism with one data set per run, PNG / SVG, CSV)
- `rules.py` - the tracking rules: main channel + helper channels (V3.0), the older
  ONLY / WITH / AND / IF (applied exactly), helper image and 1 um guard
- `detectors.py`, `gui/traindlg.py` - trained auto-detect (V3.0): learns which cells you
  pick from your hand-analysed runs; scoreboard, quiz, saved buttons
- `measure.py`, `nd2io.py`, `config.py` - the measurements, reading the .nd2, settings
  (V3.0: the ratio check - F/F0 / ratio / R/R0 only where a channel is clearly above
  background at baseline)
- `segment.py`, `compartments.py` - the ROI object, image helpers, background region,
  mitochondria and whole-cell helpers used when you click
- `qc.py` - the quality checks that exclude a cell (with the reason shown)
- `safety.py` - file names, never-overwrite output files, and long Windows paths (every
  file is written and read with the extended-length form, so results deeper than 260
  characters still work)
