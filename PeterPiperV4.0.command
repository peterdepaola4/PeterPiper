#!/bin/bash
# =====================================================================
#  PeterPiperV4.0 for macOS - the only file you need to double-click.
#  (On Windows, double-click PeterPiperV4.0.bat in this same folder:
#  the same program, the same files.)
#
#  First time on a Mac: it installs what it needs (about 5 min, needs
#  internet once). Every time after that: it just opens, and everything
#  runs on this Mac (nothing is uploaded).
#
#  The FIRST time macOS may say it cannot check this file (it is not
#  registered with Apple): right-click (or Control-click) it > Open >
#  Open; on newer macOS: System Settings > Privacy & Security > Open
#  Anyway. After the first start the PeterPiper folder is marked as
#  checked, so it opens with a double-click from then on.
#
#  The install lives in  ~/.PeterPiperV4.0/venv  (delete that folder to
#  start fresh). It is the same as the Windows launcher's:
#   - a 64-bit Python 3.11 - 3.14 on this Mac (3.10: compatible versions);
#     if there is none, it offers to download one with the small "uv" tool
#     (a pinned uv release, checked against its SHA-256 before it runs;
#     Python from the official python-build-standalone builds), all inside
#     ~/.PeterPiperV4.0 - nothing else on the Mac changes;
#   - the exact tested package versions (app/requirements.txt), else the
#     compatible ones (app/requirements-compatible.txt), and the versions
#     really installed in venv/installed_versions.txt;
#   - the first time: a PeterPiper app in your Applications folder
#     (~/Applications: Spotlight, Launchpad, the Dock) and on the Desktop.
#
#  IT / testing: PETERPIPER_HOME puts the install somewhere else;
#  PETERPIPER_INSTALL_ONLY=1 installs / checks only (the app is not
#  opened); PETERPIPER_NO_SHORTCUTS=1 makes no app / Desktop alias;
#  PETERPIPER_UV=yes / no answers the download question without asking;
#  PETERPIPER_USE_UV=1 skips the search and always uses uv;
#  PETERPIPER_UV_FILE=<file> uses a copy of the uv archive already on this
#  Mac (no download; still checked against the SHA-256).
#  "PeterPiperV4.0.command --selftest [folder]" installs if needed, then runs
#  PeterPiper's self-test in this window instead of opening it.
#
#  Works with the bash that comes with macOS (3.2): no newer bash features.
# =====================================================================

# other software's Python / pip / uv settings must not reach PeterPiper's Python
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP

PP_NAME="PeterPiperV4.0"
PP_TITLE="PeterPiper 4.0"
# the uv tool, used only when no suitable Python is found: a pinned release and
# the SHA-256 of its macOS archives, as published with that release
PPUV_VERSION="0.12.24"
PPUV_SHA256_ARM64="0c4346de7abdb49495b393b9ec809fe387aa43e586be20fecb972216c1e71732"
PPUV_SHA256_X86_64="4fa82e37cb94767661f532b001e470b67a186c7260e305bd84ddb78fd545c0b6"
PPUV_PY="3.11"
MODS="numpy scipy skimage PIL skimage.registration skimage.segmentation tifffile imagecodecs nd2 dask openpyxl PySide6.QtWidgets pyqtgraph matplotlib"

say() { printf '%s\n' "$*"; }

# ------------------------------------------------------------------ helpers
pp_sha256() {
    # the SHA-256 of a file, lower case ('' when it cannot be computed)
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" 2>/dev/null | awk '{print tolower($1)}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print tolower($1)}'
    fi
}

pp_verify_sha256() {
    # 0 when file $1 has the SHA-256 $2 (any case), else 1
    local got want
    got="$(pp_sha256 "$1")"
    want="$(printf '%s' "$2" | tr 'A-F' 'a-f')"
    [ -n "$got" ] && [ "$got" = "$want" ]
}

pp_uv_asset() {
    # "<archive name> <sha256>" of the uv build for this Mac's processor
    local arm
    arm="$(sysctl -n hw.optional.arm64 2>/dev/null)"
    if [ "$arm" = "1" ] || [ "$(uname -m)" = "arm64" ]; then
        say "uv-aarch64-apple-darwin.tar.gz $PPUV_SHA256_ARM64"
    elif [ "$(uname -m)" = "x86_64" ]; then
        say "uv-x86_64-apple-darwin.tar.gz $PPUV_SHA256_X86_64"
    else
        return 1
    fi
}

pp_trypy() {
    # use the Python "$1" if it is 64-bit 3.10 - 3.14 (sets PY; ANYPY = the first that runs)
    [ -n "$1" ] || return 0
    [ -x "$1" ] || command -v "$1" >/dev/null 2>&1 || return 0
    "$1" --version </dev/null >/dev/null 2>&1 || return 0
    [ -n "$ANYPY" ] || ANYPY="$1"
    if "$1" -c "import sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,14) and sys.maxsize>2**32 else 1)" </dev/null >/dev/null 2>&1; then
        PY="$1"
    fi
    return 0
}

pp_find_python() {
    # 3.11 - 3.14 first (the exact tested versions exist for these), then 3.10.
    # Apple's /usr/bin/python3 is never used: it is too old (3.9), and on a Mac
    # without Apple's developer tools it opens a window offering to install them.
    local v d c
    for v in 3.11 3.12 3.13 3.14 3.10; do
        for c in "$(command -v "python$v" 2>/dev/null)" \
                 "/Library/Frameworks/Python.framework/Versions/$v/bin/python$v" \
                 "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v" \
                 "/opt/homebrew/opt/python@$v/bin/python$v" "/usr/local/opt/python@$v/bin/python$v"; do
            [ -n "$PY" ] && return 0
            [ -n "$c" ] && [ "$c" != "/usr/bin/python$v" ] && pp_trypy "$c"
        done
    done
    for d in python3 python; do
        [ -n "$PY" ] && return 0
        c="$(command -v "$d" 2>/dev/null)"
        case "$c" in
            ""|/usr/bin/*) ;;
            *) pp_trypy "$c" ;;
        esac
    done
    return 0
}

pp_uvenv() {
    # uv's settings: everything stays in HOME_DIR; uv settings of other software
    # are ignored; uv only uses the Pythons it downloaded itself
    local v
    for v in $(env | sed -n 's/^\(UV_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$v"; done
    export UV_PYTHON_INSTALL_DIR="$HOME_DIR/python"
    export UV_PYTHON_BIN_DIR="$HOME_DIR/python/bin"
    export UV_CACHE_DIR="$HOME_DIR/uv/cache"
    export UV_NO_CONFIG=1
    export UV_PYTHON_PREFERENCE=only-managed
}

pp_uvfind() {
    # the Python that uv downloaded at an earlier install (no question, no download)
    [ -x "$UVEXE" ] || return 0
    pp_uvenv
    local p
    p="$("$UVEXE" python find "$PPUV_PY" 2>/dev/null </dev/null | head -n 1)"
    [ -n "$p" ] && [ -x "$p" ] && pp_trypy "$p"
    return 0
}

pp_uv_get() {
    # download the pinned uv, check its SHA-256, then let it download Python.
    # 0 = PY is set; 1 = download / install problem; 3 = wrong SHA-256 (deleted)
    local line asset sha url tgz
    line="$(pp_uv_asset)" || { say "  This Mac's processor is not one uv is made for."; return 1; }
    asset="${line%% *}"
    sha="${line##* }"
    url="https://github.com/astral-sh/uv/releases/download/$PPUV_VERSION/$asset"
    mkdir -p "$HOME_DIR/uv" || return 1
    tgz="$HOME_DIR/uv/$asset"
    if [ -n "$PETERPIPER_UV_FILE" ]; then
        say "        using the copy in \"$PETERPIPER_UV_FILE\""
        cp "$PETERPIPER_UV_FILE" "$tgz" || return 1
    else
        say "        downloading uv, about 15 MB, from $url"
        curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
             --silent --show-error --connect-timeout 30 --output "$tgz" "$url" || {
            rm -f "$tgz"; return 1; }
    fi
    if ! pp_verify_sha256 "$tgz" "$sha"; then
        say "  The downloaded file is NOT the published uv release (its SHA-256 differs):"
        say "  expected $sha"
        say "  got      $(pp_sha256 "$tgz")"
        say "  It was deleted and nothing was run."
        rm -f "$tgz"
        return 3
    fi
    say "        SHA-256 checked: it is the published uv release."
    tar -xzf "$tgz" -C "$HOME_DIR/uv" --strip-components 1 || { rm -f "$tgz"; return 1; }
    rm -f "$tgz"
    [ -x "$UVEXE" ] || return 1
    pp_uvenv
    say "        downloading Python $PPUV_PY (about 25 MB) ..."
    "$UVEXE" python install "$PPUV_PY" --no-bin </dev/null || return 1
    pp_uvfind
    [ -n "$PY" ] || return 1
    return 0
}

pp_uv_offer() {
    # no suitable Python: offer uv. Sets PY, or UVFAIL=1 when uv was tried and failed
    local ans
    ans="$PETERPIPER_UV"
    if [ "$PETERPIPER_USE_UV" = "1" ] && [ -z "$ans" ]; then ans="yes"; fi
    if [ -z "$ans" ]; then
        [ -n "$NOASK" ] && return 0
        say ""
        say "  No suitable Python was found on this Mac."
        say ""
        say "  PeterPiper needs Python 3.11+. Download it automatically now"
        say "  (about 40 MB, from the official uv / python-build-standalone releases)?"
        say "  It goes into PeterPiper's own folder only:"
        say "  $HOME_DIR"
        say ""
        printf '  Type Y and press Return for yes, or N for no [Y/n]: '
        read -r ans || ans="n"
    fi
    case "$ans" in
        ""|[Yy]*) ;;
        *) return 0 ;;
    esac
    say ""
    say "  Getting Python with uv $PPUV_VERSION ..."
    pp_uv_get || UVFAIL=1
    say ""
    return 0
}

pp_logo() {
    # the PeterPiper logo in block characters, the widest that fits this window
    local cols art
    cols="$(tput cols 2>/dev/null)"
    case "$cols" in ''|*[!0-9]*) cols=80 ;; esac
    art=""
    [ "$cols" -ge 74 ] && art="$ASSETS/logo_72.txt"
    [ "$cols" -ge 102 ] && art="$ASSETS/logo_100.txt"
    [ "$cols" -ge 118 ] && art="$ASSETS/logo_116.txt"
    say ""
    if [ -n "$art" ] && [ -f "$art" ] && iconv -f UTF-16 -t UTF-8 "$art" 2>/dev/null | tr -d '\r'; then
        say ""
    else
        say "  $PP_TITLE"
        say ""
    fi
}

pp_wait() {
    # wait for Return, except when nobody is there to press it
    [ -n "$NOASK" ] && return 0
    printf '  Press Return to close this window.'
    read -r _ || true
}

pp_pipinstall() {
    # pip install of the list $1 into the private Python, with the progress helper
    if [ -f "$APP/install_progress.py" ]; then
        "$VPY" "$APP/install_progress.py" install "$1" $PIPOPT
    else
        "$VPY" -m pip install $PIPOPT -r "$1"
    fi
}

pp_checkpkgs() {
    if [ -f "$APP/install_progress.py" ]; then
        "$VPY" "$APP/install_progress.py" check $MODS
    else
        "$VPY" -c "import numpy,scipy,skimage,PIL,skimage.registration,skimage.segmentation,tifffile,imagecodecs,nd2,dask,openpyxl,PySide6.QtWidgets,pyqtgraph,matplotlib;print('   all packages OK')"
    fi
}

pp_unquarantine() {
    # after a start that worked: the PeterPiper folder is no longer "from the
    # internet", so macOS does not ask again (the user already said Open once)
    if xattr -p com.apple.quarantine "$SELF" >/dev/null 2>&1; then
        xattr -dr com.apple.quarantine "$HERE" >/dev/null 2>&1 || true
    fi
}

pp_shortcuts() {
    # the PeterPiper app in ~/Applications and a Desktop alias, once per folder
    # (made again only when this folder has moved: shortcuts_for.txt)
    [ -n "$PETERPIPER_NO_SHORTCUTS" ] && return 0
    [ -f "$APP/peterpiper/platforms.py" ] || return 0
    local made=""
    [ -f "$HOME_DIR/shortcuts_for.txt" ] && made="$(head -n 1 "$HOME_DIR/shortcuts_for.txt")"
    [ "$made" = "$SELF" ] && [ -d "$HOME/Applications/PeterPiper.app" ] && return 0
    if "$VPY" "$APP/peterpiper/platforms.py" shortcuts "$SELF" >/dev/null 2>&1; then
        say "$SELF" > "$HOME_DIR/shortcuts_for.txt"
        say "  A PeterPiper app is now in your Applications folder (find it with"
        say "  Spotlight or Launchpad, keep it in the Dock) and on your Desktop -"
        say "  use it to start PeterPiper from now on."
        say ""
    fi
    return 0
}

# ------------------------------------------------------------------ the steps
pp_main() {
    SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    HERE="$(dirname "$SELF")"
    APP="$HERE/app"
    ASSETS="$APP/peterpiper/assets"
    HOME_DIR="$HOME/.$PP_NAME"
    [ -n "$PETERPIPER_HOME" ] && HOME_DIR="$PETERPIPER_HOME"
    ENV="$HOME_DIR/venv"
    LOG="$HOME_DIR/error_$$_$RANDOM.txt"
    STAMP="$ENV/installed_requirements.txt"
    UVEXE="$HOME_DIR/uv/uv"
    ONLY=""; [ "$PETERPIPER_INSTALL_ONLY" = "1" ] && ONLY=1
    SELFTEST=""; [ "$1" = "--selftest" ] && SELFTEST=1
    NOASK=""; { [ -n "$ONLY" ] || [ -n "$SELFTEST" ]; } && NOASK=1
    FROM_APP="$PETERPIPER_FROM_APP"
    unset PETERPIPER_FROM_APP
    FRESH=""; COMPAT=""; PY=""; ANYPY=""; UVFAIL=""

    if [ "$(uname -s)" != "Darwin" ] && [ -z "$PETERPIPER_ANY_SYSTEM" ]; then
        say ""
        say "  $PP_NAME.command is for macOS. On Windows, double-click $PP_NAME.bat."
        return 1
    fi

    # ---- 1. A complete PeterPiper folder? -------------------------------
    if [ ! -f "$APP/PeterPiper.py" ] || [ ! -f "$APP/requirements.txt" ]; then
        say ""
        say "  $PP_NAME cannot start: the folder 'app' is not next to this file."
        say ""
        say "  1. Double-click the zip file $PP_NAME.zip (it unpacks itself)."
        say "  2. Open the unpacked folder $PP_NAME and double-click"
        say "     $PP_NAME.command there."
        say ""
        pp_wait
        return 1
    fi
    mkdir -p "$HOME_DIR" || { say "  Cannot make the folder $HOME_DIR"; pp_wait; return 1; }

    # ---- 2. Installed and up to date? Then just open --------------------
    # reuse an earlier version's identical install instead of installing again
    # (only if its Python still starts), newest first
    if [ -z "$PETERPIPER_HOME" ] && [ ! -x "$ENV/bin/python" ]; then
        local p
        for p in .PeterPiperV1.2 .PeterPiperV1.1 .PeterPiperV1.0; do
            if [ -f "$HOME/$p/venv/installed_requirements.txt" ] \
               && cmp -s "$HOME/$p/venv/installed_requirements.txt" "$APP/requirements.txt" \
               && "$HOME/$p/venv/bin/python" -c "" </dev/null >/dev/null 2>&1; then
                ENV="$HOME/$p/venv"
                STAMP="$ENV/installed_requirements.txt"
                break
            fi
        done
    fi
    VPY="$ENV/bin/python"
    if [ -x "$VPY" ] && [ -f "$STAMP" ] && cmp -s "$STAMP" "$APP/requirements.txt" \
       && "$VPY" -c "" </dev/null >/dev/null 2>&1; then
        pp_launch "$@"
        return $?
    fi
    # an install is needed: started from the PeterPiper app (no window), open
    # this file in Terminal so the progress can be seen
    if [ -n "$FROM_APP" ] && [ -z "$NOASK" ]; then
        open -a Terminal "$SELF"
        return 0
    fi
    pp_install "$@" || return $?
    pp_launch "$@"
    return $?
}

pp_install() {
    FRESH=1
    [ -z "$ONLY" ] && clear 2>/dev/null
    pp_logo
    say "  $PP_TITLE - first-time setup"
    say "  ---------------------------------"
    say ""
    say "  Installing what $PP_NAME needs. This happens only once"
    say "  and takes about 5 minutes. Please keep this window open."
    say ""
    say "  ############################################################"
    say "  #                                                          #"
    say "  #          PLEASE WAIT FOR INSTALLATIONS TO FINISH         #"
    say "  #                                                          #"
    say "  #   This takes about 5 minutes, only the first time.       #"
    say "  #   The window may LOOK FROZEN for several minutes - that  #"
    say "  #   is normal, it is still working. DO NOT CLOSE IT.       #"
    say "  #   PeterPiper opens by itself when it is installed.       #"
    say "  #                                                          #"
    say "  ############################################################"
    say ""
    case "$HERE" in
        */Library/CloudStorage/*|*/Library/Mobile\ Documents/*)
            say "  Tip: this folder is in iCloud / a cloud folder. PeterPiper works best"
            say "  from a folder on this Mac (e.g. your home folder or Applications)."
            say "" ;;
    esac

    # ---- find a 64-bit Python 3.11 - 3.14 (3.10: compatible versions) ----
    [ "$PETERPIPER_USE_UV" = "1" ] || pp_find_python
    [ -n "$PY" ] || pp_uvfind
    [ -n "$PY" ] || pp_uv_offer
    if [ -n "$UVFAIL" ]; then pp_msg_uvfail; return 1; fi
    if [ -z "$PY" ]; then
        if [ -n "$ANYPY" ]; then pp_msg_badpython; else pp_msg_nopython; fi
        return 1
    fi
    say "  Using:"
    "$PY" --version
    say ""

    if [ ! -x "$ENV/bin/python" ] || ! "$ENV/bin/python" -m pip --version </dev/null >/dev/null 2>&1; then
        [ -e "$ENV" ] && say "  The private Python from an earlier attempt does not work any more" \
                      && say "  - setting it up again."
        say "  [1/3] Setting up a private Python ..."
        say "        (about 10-30 seconds; nothing is downloaded yet)"
        if ! "$PY" -m venv --clear "$ENV"; then
            say ""
            say "  Could not set up the private Python (the message above says why)."
            say "  Most often: the folder is in iCloud or on a network drive. Move the"
            say "  $PP_NAME folder to a folder on this Mac and try again."
            say ""
            pp_wait
            return 1
        fi
    fi
    VPY="$ENV/bin/python"
    STAMP="$ENV/installed_requirements.txt"

    # ignore any pip settings that could change where packages come from
    local v
    for v in $(env | sed -n 's/^\(PIP_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$v"; done
    export PIP_CONFIG_FILE=/dev/null
    # ready-made packages (wheels) only, from the official index over https,
    # into the private Python only; pip itself is never upgraded
    PIPOPT="--require-virtualenv --index-url https://pypi.org/simple --only-binary=:all: --no-input --disable-pip-version-check --no-cache-dir --progress-bar on"

    local list="requirements.txt - the exact versions $PP_NAME was tested with"
    local exact=1
    "$VPY" -c "import sys;sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,14) and sys.version_info[:3]!=(3,14,1) else 1)" || exact=""
    if [ -n "$exact" ]; then
        say "  [2/3] Downloading packages: the exact versions $PP_NAME was"
        say "        tested with - about 250 MB, progress bars below ..."
        say ""
        say "  PLEASE WAIT: when the text stops at \"Installing collected packages\""
        say "  it is still working (2-5 minutes). Do not close this window."
        say "  Every few seconds a \"still working\" line says what it is doing."
        say ""
        if ! pp_pipinstall "$APP/requirements.txt"; then
            say ""
            say "  The exact tested versions could not be installed on this Mac"
            say "  - the message above says why. Trying the compatible versions instead ..."
            say ""
            exact=""
        fi
    else
        say "  This Python cannot use the exact tested package versions - they"
        say "  need Python 3.11 - 3.14 (not 3.14.1) - so compatible versions are installed."
        say ""
    fi
    if [ -z "$exact" ]; then
        COMPAT=1
        list="requirements-compatible.txt - compatible versions, NOT the exact tested ones"
        say "  [2/3] Downloading packages: compatible versions - about 250 MB,"
        say "        progress bars below ..."
        say ""
        if ! pp_pipinstall "$APP/requirements-compatible.txt"; then
            say ""
            say "  Downloading the packages failed (the message above says why)."
            say "  Usually: no internet, or a firewall blocking pypi.org."
            say "  Fix the connection and double-click this file again - it carries"
            say "  on from where it stopped. If it keeps failing, delete the folder"
            say "  \"$ENV\""
            say "  and try again (a completely fresh install)."
            say ""
            pp_wait
            return 1
        fi
    fi

    say ""
    say "  [3/3] Checking that every package loads (about 10-30 seconds) ..."
    if ! pp_checkpkgs; then
        say ""
        say "  The packages were downloaded, but the check that they load FAILED"
        say "  (the message above says which one). Delete the folder"
        say "  \"$ENV\""
        say "  and double-click this file again (a completely fresh install). If it"
        say "  fails again, send a screenshot of this window to whoever maintains"
        say "  $PP_NAME."
        say ""
        pp_wait
        return 1
    fi

    # record what was really installed (for methods sections and bug reports)
    {
        say "# $PP_NAME install, $(date '+%Y-%m-%d %H:%M:%S')"
        say "# package list: $list"
        "$VPY" -c "import sys,platform;print('# Python '+sys.version.split()[0]+', '+platform.platform())"
        "$VPY" -m pip freeze --disable-pip-version-check
    } > "$ENV/installed_versions.txt"
    cp "$APP/requirements.txt" "$STAMP"
    pp_unquarantine

    say ""
    say "  Setup finished."
    if [ -n "$COMPAT" ]; then
        say ""
        say "  NOTE: this Mac got COMPATIBLE package versions, not the exact"
        say "  ones $PP_NAME was tested with. The app works the same way; for"
        say "  published work, report the versions listed in"
        say "  \"$ENV/installed_versions.txt\""
        say ""
        say "  To try the exact tested versions again later (for example after"
        say "  installing Python 3.13 from python.org, or on macOS 14 or newer),"
        say "  delete the folder"
        say "  \"$ENV\""
        say "  and double-click this file again."
        say ""
        pp_wait
    fi
    return 0
}

pp_launch() {
    VPY="$ENV/bin/python"
    if [ -n "$SELFTEST" ]; then
        say ""
        [ -z "$FRESH" ] && say "  Already installed and up to date - nothing was downloaded."
        say "  Running the PeterPiper self-test with \"$ENV\" ..."
        say ""
        shift
        "$VPY" -X faulthandler "$APP/PeterPiper.py" --selftest "$@"
        return $?
    fi
    if [ -n "$ONLY" ]; then
        say ""
        [ -z "$FRESH" ] && say "  Already installed and up to date - nothing was downloaded."
        say "  PETERPIPER_INSTALL_ONLY=1: install checked in \"$ENV\""
        say "  The app was not opened."
        return 0
    fi
    pp_unquarantine
    if [ -z "$FROM_APP" ]; then
        [ -n "$FRESH" ] || clear 2>/dev/null
        pp_logo
        if [ -n "$FRESH" ]; then
            say "  Starting PeterPiper - the window opens in about 10-20 seconds."
        else
            say "  Starting PeterPiper - the window opens in a few seconds."
        fi
        say "  $PP_TITLE runs in its own window."
        say "  Keep this window open while you work - you can close it when you"
        say "  quit PeterPiper."
        say ""
    fi
    pp_shortcuts
    # anything printed (a Python error, or a crash report from -X faulthandler)
    # goes to the log, so a problem is never lost
    "$VPY" -X faulthandler "$APP/PeterPiper.py" 2> "$LOG"
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        rm -f "$LOG"
        return 0
    fi
    say "$PP_NAME exit code $rc" >> "$LOG"
    if [ -n "$FROM_APP" ]; then
        open -e "$LOG" >/dev/null 2>&1
        return 1
    fi
    say ""
    say "  $PP_NAME closed unexpectedly. Opening the error report ..."
    say "  (Send that file to whoever maintains $PP_NAME.)"
    say "  $LOG"
    say ""
    tail -n 20 "$LOG" | sed 's/^/    /'
    open -e "$LOG" >/dev/null 2>&1
    say ""
    pp_wait
    return 1
}

pp_msg_nopython() {
    say ""
    say "  Python is not installed on this Mac (or only Apple's old one)."
    say ""
    say "  1. Go to  https://www.python.org/downloads/macos/"
    say "  2. Download the newest Python 3.13 \"macOS 64-bit universal2 installer\""
    say "     and run it."
    say "  3. Then double-click  $PP_NAME.command  again."
    say ""
    say "  (Or double-click $PP_NAME.command again and answer Y when it offers"
    say "  to download Python by itself.)"
    say ""
    [ -z "$NOASK" ] && open "https://www.python.org/downloads/macos/" >/dev/null 2>&1
    pp_wait
}

pp_msg_badpython() {
    say ""
    say "  This Mac's Python cannot run $PP_NAME:"
    "$ANYPY" --version </dev/null 2>&1 | sed 's/^/  /'
    say "  $PP_NAME needs 64-bit Python 3.10 - 3.14 (3.11 - 3.14 is best)."
    say "  Python 3.15 and newer are not supported yet (the packages $PP_NAME"
    say "  needs are not available for them)."
    say "  You can keep your Python: the one below is installed next to it."
    say "  Install Python 3.13 from https://www.python.org/downloads/macos/"
    say "  (\"macOS 64-bit universal2 installer\"), then double-click this file again."
    say ""
    [ -z "$NOASK" ] && open "https://www.python.org/downloads/macos/" >/dev/null 2>&1
    pp_wait
}

pp_msg_uvfail() {
    say ""
    say "  Python could not be downloaded automatically (the message above says"
    say "  why). Nothing was installed and nothing of yours was changed."
    say "  Usually: no internet, or a firewall blocking github.com."
    say ""
    say "  Instead, install Python yourself:"
    say "  1. Go to  https://www.python.org/downloads/macos/"
    say "  2. Download Python 3.13 (\"macOS 64-bit universal2 installer\") and run it."
    say "  3. Then double-click  $PP_NAME.command  again."
    say ""
    pp_wait
}

# tests load the functions above without running anything
if [ "$PETERPIPER_SOURCE_ONLY" != "1" ]; then
    pp_main "$@"
    exit $?
fi
