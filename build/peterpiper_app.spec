# -*- mode: python -*-
"""
Developer tool (not shipped): PyInstaller recipe for the self-contained app -
PeterPiper.app on macOS, a PeterPiper folder with PeterPiper.exe on Windows.
The app carries its own Python and every package (the versions in
app/requirements.txt), so nothing has to be installed to run it.

    pip install -r app/requirements.txt pyinstaller
    pyinstaller --noconfirm --distpath build/dist --workpath build/work build/peterpiper_app.spec

Must be run ON the system it builds for (a Mac app is built on a Mac - see
.github/workflows/mac-app.yml, which does it on GitHub's Mac machines). Check
the result with:  <app> --selftest   (macOS: PeterPiper.app/Contents/MacOS/PeterPiper)
"""
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

HERE = Path(SPECPATH)                      # noqa: F821 (set by PyInstaller)
REPO = HERE.parent
APP = REPO / "app"
ASSETS = APP / "peterpiper" / "assets"
sys.path.insert(0, str(APP))               # so PeterPiper's own package is found below
VERSION = re.search(r'__version__ = "([^"]+)"',
                    (APP / "peterpiper" / "__init__.py").read_text(encoding="utf-8")).group(1)

# PeterPiper's own data (logo, Prism templates) and every module, including the
# ones only loaded when needed; the .nd2 reader's modules likewise (its OME-Zarr
# export is an optional extra PeterPiper does not use)
datas = collect_data_files("peterpiper")
# the .nd2 reader's metadata (OME) code finds its xsdata plugins by their installed
# package records at run time, so the modules AND those records go in
OME = ["ome_types", "xsdata", "xsdata_pydantic_basemodel"]
hidden = (collect_submodules("peterpiper")
          + collect_submodules("nd2", filter=lambda n: "_ome_zarr" not in n)
          + [m for pkg in OME for m in collect_submodules(pkg)]
          + ["PySide6.QtSvg"])
for pkg in OME:
    datas += collect_data_files(pkg)
for dist in ("nd2", "ome-types", "xsdata", "xsdata-pydantic-basemodel", "pydantic",
             "pydantic-extra-types"):
    try:
        datas += copy_metadata(dist)
    except Exception:                      # noqa: BLE001 (not installed: nothing to copy)
        pass
excludes = ["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "pytest", "PySide6.QtWebEngineCore",
            "PySide6.Qt3DCore", "PySide6.QtQuick3D"]

a = Analysis(                              # noqa: F821
    [str(APP / "PeterPiper.py")],
    pathex=[str(APP)],
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)                          # noqa: F821
icon = str(ASSETS / ("PeterPiper.icns" if sys.platform == "darwin" else "PeterPiper.ico"))
exe = EXE(                                 # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PeterPiper",
    console=False,                         # a window app, no terminal
    icon=icon,
    argv_emulation=False,
    target_arch=None,                      # the Python running the build (arm64 or x86_64)
)
coll = COLLECT(exe, a.binaries, a.datas, name="PeterPiper")   # noqa: F821
if sys.platform == "darwin":
    app = BUNDLE(                          # noqa: F821
        coll,
        name="PeterPiper.app",
        icon=icon,
        bundle_identifier="io.github.peterdepaola4.peterpiper",
        version=VERSION,
        info_plist={
            "CFBundleName": "PeterPiper",
            "CFBundleDisplayName": "PeterPiper",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHumanReadableCopyright": "Copyright (c) 2026 Peter DePaola IV. MIT License.",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",
            "LSApplicationCategoryType": "public.app-category.education",
        },
    )
