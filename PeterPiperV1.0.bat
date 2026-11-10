@echo off
setlocal DisableDelayedExpansion
rem other software's Python settings must not reach PeterPiper's private Python
set "PYTHONHOME="
set "PYTHONPATH="
title PeterPiper 1.0
rem ===================================================================
rem  PeterPiperV1.0 - the only file you need to double-click.
rem
rem  First time on a computer: it installs what it needs (about 5 min,
rem  needs internet once). Every time after that: it just opens, and
rem  everything runs on this computer (nothing is uploaded).
rem
rem  The install lives in  %USERPROFILE%\.PeterPiperV1.0\venv
rem  (delete that folder to start fresh). IT / testing: set PETERPIPER_HOME
rem  to put the install somewhere else; set PETERPIPER_INSTALL_ONLY=1 to
rem  install / check only, without opening the app; set
rem  PETERPIPER_NO_SHORTCUTS=1 to make no shortcuts.
rem
rem  Each start shows the PeterPiper logo in this window (drawn with
rem  block characters, app\peterpiper\assets\logo_*.txt) and, the first
rem  time, puts a PeterPiper shortcut with the logo icon next to this file,
rem  on the Desktop and in the Start menu (a .bat file cannot have its own
rem  icon). The shortcuts are made again if this folder is moved.
rem
rem  Package versions: app\requirements.txt lists the exact versions the
rem  app was tested with. If they cannot be installed on this computer,
rem  app\requirements-compatible.txt is used instead and the window says
rem  so. The versions really installed are written to
rem  venv\installed_versions.txt
rem ===================================================================

set "HERE=%~dp0"
set "APP=%HERE%app"
set "HOME_DIR=%USERPROFILE%\.PeterPiperV1.0"
if defined PETERPIPER_HOME set "HOME_DIR=%PETERPIPER_HOME%"
set "ENV=%HOME_DIR%\venv"
rem a log per launch, so a second copy of the app can open while one is running
set "LOG=%HOME_DIR%\error_%RANDOM%%RANDOM%.txt"
set "STAMP=%ENV%\installed_requirements.txt"
set "ONLY="
if "%PETERPIPER_INSTALL_ONLY%"=="1" set "ONLY=1"
rem the messages below wait for a key press, except in install-only mode
set "WAIT=pause"
if defined ONLY set "WAIT=rem"
set "FRESH="
set "COMPAT="
set "ASSETS=%APP%\peterpiper\assets"

rem ---- 1. Opened from inside the zip? ------------------------------
if not exist "%APP%\PeterPiper.py" goto notextracted
if not exist "%APP%\requirements.txt" goto notextracted

if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"

rem ---- 2. Installed and up to date? Then just open ------------------
rem reuse an earlier version's identical install instead of installing again
rem (only if its Python still starts: its base Python may have been uninstalled)
if defined PETERPIPER_HOME goto checkenv
if exist "%ENV%\Scripts\pythonw.exe" goto checkenv
set "PREV="
for %%P in (.PD4navV3.0 .PD4navV2.9 .PD4navV2.8 .PD4navV2.7 .PD4navV2.6 .PD4navV2.5 .PD4navV2.4 .PD4navV2.3 .PD4navV2.2 .PD4navV2.1) do (
    if not defined PREV if exist "%USERPROFILE%\%%P\venv\installed_requirements.txt" (
        fc /b "%USERPROFILE%\%%P\venv\installed_requirements.txt" "%APP%\requirements.txt" >nul 2>&1 && "%USERPROFILE%\%%P\venv\Scripts\python.exe" -c "" <nul >nul 2>&1 && set "PREV=%USERPROFILE%\%%P\venv"
    )
)
if not defined PREV goto checkenv
set "ENV=%PREV%"
set "STAMP=%PREV%\installed_requirements.txt"
:checkenv
if not exist "%ENV%\Scripts\pythonw.exe" goto install
if not exist "%STAMP%" goto install
fc /b "%STAMP%" "%APP%\requirements.txt" >nul 2>&1 || goto install
rem the private Python stops working if the Python it was made from is
rem uninstalled: then it is set up again
"%ENV%\Scripts\python.exe" -c "" <nul >nul 2>&1 || goto install
goto launch

rem ===================================================================
:install
set "FRESH=1"
if not defined ONLY cls
call :logo
echo   PeterPiper 1.0 - first-time setup
echo   ---------------------------------
echo.
echo   Installing what PeterPiperV1.0 needs. This happens only once
echo   and takes about 5 minutes. Please keep this window open.
echo.
title PLEASE WAIT FOR INSTALLATIONS - do not close this window
echo   ############################################################
echo   #                                                          #
echo   #          PLEASE WAIT FOR INSTALLATIONS TO FINISH         #
echo   #                                                          #
echo   #   This takes about 5 minutes, only the first time.       #
echo   #   The window may LOOK FROZEN for several minutes - that  #
echo   #   is normal, it is still working. DO NOT CLOSE IT.       #
echo   #   PeterPiper opens by itself when it is installed.       #
echo   #                                                          #
echo   ############################################################
echo.

rem ---- find 64-bit Python: 3.11 - 3.14 first, because the exact tested
rem      package versions exist for these; then 3.10, which gets the
rem      compatible versions. Each probe reads from nul, so a launcher that
rem      offers to install a missing version cannot wait for an answer.
set "PY="
set "ANYPY="
for %%V in (3.11 3.12 3.13 3.14 3.10) do if not defined PY call :trypy py -%%V
if not defined PY call :trypy py -3
if not defined PY call :trypy python
if not defined PY call :trypy python3
if not defined PY if defined ANYPY goto badpython
if not defined PY goto nopython
echo   Using:
call %PY% --version
echo.

rem a long install path breaks the install: Windows limits a path to 260
rem characters (unless "long paths" are turned on) and the longest file in
rem the packages needs about 170 of them
set "LONGOK="
reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2>nul | "%SystemRoot%\System32\findstr.exe" /c:"0x1" >nul && set "LONGOK=1"
if defined LONGOK goto pathok
call %PY% -c "import sys;sys.exit(7 if len(sys.argv[1])>85 else 0)" "%ENV%" <nul
if errorlevel 7 if not errorlevel 8 goto longpath
:pathok
if not exist "%ENV%\Scripts\python.exe" goto makevenv
"%ENV%\Scripts\python.exe" -m pip --version <nul >nul 2>&1 && goto havevenv
echo   The private Python from an earlier attempt does not work any more
echo   - setting it up again.
:makevenv
echo   [1/3] Setting up a private Python ...
call %PY% -m venv --clear "%ENV%"
if errorlevel 1 goto venvfail
:havevenv
set "VPY=%ENV%\Scripts\python.exe"

rem ignore any pip settings that could change where packages come from
for /f "tokens=1 delims==" %%V in ('set PIP_ 2^>nul') do set "%%V="
set "PIP_CONFIG_FILE=nul"
rem ready-made packages (wheels) only, from the official index over https,
rem into the private Python only; pip itself is never upgraded
set "PIPOPT=--require-virtualenv --index-url https://pypi.org/simple --only-binary=:all: --no-input --disable-pip-version-check --no-cache-dir --progress-bar on"

rem the exact tested versions exist for Python 3.11 - 3.14 only (not 3.14.1:
rem networkx, needed by scikit-image, refuses that one release)
"%VPY%" -c "import sys;sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,14) and sys.version_info[:3]!=(3,14,1) else 1)"
if errorlevel 1 goto compatonly
set "LIST=requirements.txt - the exact versions PeterPiperV1.0 was tested with"
echo   [2/3] Downloading packages: the exact versions PeterPiperV1.0 was
echo         tested with - about 250 MB, progress bars below ...
echo.
echo   PLEASE WAIT: when the text stops at "Installing collected packages"
echo   it is still working (2-5 minutes). Do not close this window.
echo.
"%VPY%" -m pip install %PIPOPT% -r "%APP%\requirements.txt"
if not errorlevel 1 goto check
echo.
echo   The exact tested versions could not be installed on this computer
echo   - the message above says why. Trying the compatible versions instead ...
echo.
goto compat

:compatonly
echo   This Python cannot use the exact tested package versions - they
echo   need Python 3.11 - 3.14 (not 3.14.1) - so compatible versions are installed.
echo.
:compat
set "COMPAT=1"
set "LIST=requirements-compatible.txt - compatible versions, NOT the exact tested ones"
echo   [2/3] Downloading packages: compatible versions - about 250 MB,
echo         progress bars below ...
echo.
echo   PLEASE WAIT: when the text stops at "Installing collected packages"
echo   it is still working (2-5 minutes). Do not close this window.
echo.
"%VPY%" -m pip install %PIPOPT% -r "%APP%\requirements-compatible.txt"
if errorlevel 1 goto pipfail

:check
echo.
echo   [3/3] Checking ...
"%VPY%" -c "import numpy,scipy,skimage,PIL,skimage.registration,skimage.segmentation,tifffile,imagecodecs,nd2,dask,openpyxl,PySide6.QtWidgets,pyqtgraph,matplotlib;print('   all packages OK')"
if errorlevel 1 goto checkfail

rem record what was really installed (for methods sections and bug reports)
> "%ENV%\installed_versions.txt" echo # PeterPiperV1.0 install, %DATE% %TIME%
>> "%ENV%\installed_versions.txt" echo # package list: %LIST%
"%VPY%" -c "import sys,platform;print('# Python '+sys.version.split()[0]+', '+platform.platform())" >> "%ENV%\installed_versions.txt"
"%VPY%" -m pip freeze --disable-pip-version-check >> "%ENV%\installed_versions.txt"
copy /y "%APP%\requirements.txt" "%STAMP%" >nul

echo.
title PeterPiper 1.0
echo   Setup finished.
if not defined COMPAT goto setupdone
echo.
echo   NOTE: this computer got COMPATIBLE package versions, not the exact
echo   ones PeterPiperV1.0 was tested with. The app works the same way; for
echo   published work, report the versions listed in
echo   "%ENV%\installed_versions.txt"
echo.
echo   To try the exact tested versions again later (for example after
echo   installing 64-bit Python 3.13, or with a working connection to
echo   pypi.org), delete the folder
echo   "%ENV%"
echo   and double-click this file again.
echo.
%WAIT%
:setupdone
if defined ONLY goto installonly
echo   Opening PeterPiper ...
ping -n 3 127.0.0.1 >nul

rem ===================================================================
:launch
if defined ONLY goto installonly
title PeterPiper 1.0
cls
call :logo
echo   PeterPiper 1.0 is open in its own window.
echo   Keep this window open while you work - it closes by itself when you
echo   quit PeterPiper.
echo.
call :shortcuts
rem pythonw opens the window with no console; anything printed (a Python
rem error, or a crash report from -X faulthandler) goes to the log so a
rem problem is never lost. Started directly, not with "start": "start"
rem does not hand the log file to pythonw. A crash inside Windows / Qt code
rem gives a NEGATIVE exit code, which "if errorlevel 1" would miss.
"%ENV%\Scripts\pythonw.exe" -X faulthandler "%APP%\PeterPiper.py" 2> "%LOG%"
if %errorlevel% neq 0 goto crashed
del "%LOG%" >nul 2>&1
exit /b 0

:installonly
echo.
if not defined FRESH echo   Already installed and up to date - nothing was downloaded.
echo   PETERPIPER_INSTALL_ONLY=1: install checked in "%ENV%"
echo   The app was not opened.
exit /b 0

rem ===================================================================
:notextracted
echo.
echo   PeterPiperV1.0 cannot run from inside the zip file.
echo.
echo   1. Close this window.
echo   2. Right-click the zip file and choose  "Extract All..."
echo   3. Open the extracted folder and double-click  PeterPiperV1.0.bat
echo.
echo   Tip: extract it somewhere simple like  D:\PeterPiperV1.0
echo   (not OneDrive, not a network drive).
echo.
%WAIT%
exit /b 1

:nopython
echo.
echo   Python is not installed on this computer.
echo.
echo   1. Go to  https://www.python.org/downloads/windows/
echo   2. Download Python 3.13 (or 3.12 / 3.11), "Windows installer (64-bit)",
echo      and run it.
echo   3. IMPORTANT: on the first screen tick  "Add python.exe to PATH".
echo   4. Then double-click  PeterPiperV1.0.bat  again.
echo.
%WAIT%
exit /b 1

:badpython
echo.
echo   This computer's Python cannot run PeterPiperV1.0:
call %ANYPY% --version <nul
echo   PeterPiperV1.0 needs 64-bit Python 3.10 - 3.14 (3.11 - 3.14 is best).
echo   Python 3.15 and newer are not supported yet (the packages PeterPiperV1.0
echo   needs are not available for them), and 32-bit Python does not work.
echo   You can keep your Python: the one below is installed next to it.
echo   Install Python 3.13 from https://www.python.org/downloads/windows/
echo   ("Windows installer (64-bit)", tick "Add python.exe to PATH"),
echo   then double-click this file again.
echo.
%WAIT%
exit /b 1

:venvfail
echo.
echo   Could not set up the private Python (the message above says why).
echo   Most often: the folder is on OneDrive or a network drive. Move the
echo   PeterPiperV1.0 folder to a local drive (e.g. D:\PeterPiperV1.0) and
echo   try again. If antivirus showed an alert, check it with IT first.
echo.
%WAIT%
exit /b 1

:checkfail
echo.
echo   The packages were downloaded, but the check that they load FAILED
echo   (the message above says which one). Most often antivirus blocked or
echo   removed a file, or the download was cut off. Delete the folder
echo   "%ENV%"
echo   and double-click this file again (a completely fresh install). If it
echo   fails again, send a screenshot of this window to whoever maintains
echo   PeterPiperV1.0.
echo.
%WAIT%
exit /b 1

:pipfail
echo.
echo   Downloading the packages failed (the message above says why).
echo   Usually: no internet, or a firewall blocking pypi.org.
echo   Fix the connection and double-click this file again - it carries
echo   on from where it stopped. If it keeps failing, delete the folder
echo   "%ENV%"
echo   and try again (a completely fresh install).
echo.
%WAIT%
exit /b 1

:longpath
echo.
echo   The install folder's path is too long for Windows (over 85 characters):
echo   "%ENV%"
echo   Set PETERPIPER_HOME to a folder with a short path (for example C:\PeterPiper),
echo   or ask IT to turn on Windows long paths, then double-click this file
echo   again.
echo.
%WAIT%
exit /b 1

:crashed
>> "%LOG%" echo PeterPiperV1.0 exit code %errorlevel%
echo.
echo   PeterPiperV1.0 closed unexpectedly. Opening the error report ...
echo   (Send that file to whoever maintains PeterPiperV1.0.)
echo.
start "" notepad "%LOG%"
pause
exit /b 1

rem ---- helper: use the Python started by "%*" if it is 64-bit 3.10 - 3.14
rem      ("call" so that a python.bat shim, e.g. pyenv-win, returns here)
:trypy
call %* --version <nul >nul 2>&1 || exit /b 0
if not defined ANYPY set "ANYPY=%*"
call %* -c "import sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,14) and sys.maxsize>2**32 else 1)" <nul >nul 2>&1 && set "PY=%*"
exit /b 0

rem ---- helper: the PeterPiper logo in block characters, the widest that
rem      fits this window (116, 100 or 72 characters; none if narrower).
rem      The files are UTF-16, which 'type' shows as they are, whatever the
rem      window's code page (UTF-8 under chcp 65001 garbled some characters).
:logo
set "COLS="
set "ROWS="
for /f "tokens=2 delims=:" %%W in ('mode con 2^>nul') do call :modenum %%W
if not defined COLS set "COLS=80"
set "ART="
if %COLS% GEQ 74 set "ART=%ASSETS%\logo_72.txt"
if %COLS% GEQ 102 set "ART=%ASSETS%\logo_100.txt"
if %COLS% GEQ 118 set "ART=%ASSETS%\logo_116.txt"
echo.
if not defined ART goto logotext
if not exist "%ART%" goto logotext
type "%ART%"
echo.
exit /b 0
:logotext
echo   PeterPiper 1.0
echo.
exit /b 0

rem 'mode con' lists Lines, then Columns: the first number is the height, the
rem second the width (anything that is not a number is passed over)
:modenum
if defined COLS exit /b 0
set "NUM="
set /a "NUM=%~1" 2>nul
if not defined NUM exit /b 0
if %NUM% LEQ 0 exit /b 0
if not defined ROWS (set "ROWS=%NUM%") else set "COLS=%NUM%"
exit /b 0

rem ---- helper: PeterPiper shortcuts with the logo icon (next to this file,
rem      Desktop, Start menu), once per folder: made again only when this
rem      folder has moved (shortcuts_for.txt remembers where they point).
rem      Paths go to PowerShell as environment variables, never as code.
:shortcuts
if defined PETERPIPER_NO_SHORTCUTS exit /b 0
set "PP_BAT=%~f0"
set "PP_DIR=%~dp0"
set "PP_ICO=%ASSETS%\PeterPiper.ico"
if not exist "%PP_ICO%" exit /b 0
set "MADE="
if exist "%HOME_DIR%\shortcuts_for.txt" set /p MADE=<"%HOME_DIR%\shortcuts_for.txt"
if /i "%MADE%"=="%PP_BAT%" exit /b 0
powershell -NoProfile -NonInteractive -Command "$w=New-Object -ComObject WScript.Shell; foreach($d in @($env:PP_DIR,[Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){ if($d){ $l=$w.CreateShortcut((Join-Path $d 'PeterPiper.lnk')); $l.TargetPath=$env:PP_BAT; $l.WorkingDirectory=$env:PP_DIR; $l.IconLocation=$env:PP_ICO+',0'; $l.Description='PeterPiper 1.0 - single-cell fluorescence time courses'; $l.Save() } }" >nul 2>&1
if errorlevel 1 exit /b 0
> "%HOME_DIR%\shortcuts_for.txt" echo %PP_BAT%
echo   A PeterPiper shortcut with the logo is on your Desktop, in the Start
echo   menu and in this folder - use it to start PeterPiper from now on.
echo.
exit /b 0
