"""
Starts PeterPiper.

Windows: the PeterPiper .bat file calls this file with the private virtual
environment's Python. macOS (and Windows) app: this is the app's own start file
(build/peterpiper_app.spec). It can also be run directly with any Python that
has the packages in requirements.txt installed.

    PeterPiper.py --selftest [folder]   checks this installation start to finish
                                        (peterpiper/selftest.py) and exits
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _app_log() -> None:
    """The packaged app has no console: anything printed, and a crash report,
    goes to a log file (macOS: ~/Library/Logs/PeterPiper; Windows: the user's
    PeterPiper data folder); an empty log is removed at a normal exit."""
    import atexit
    import faulthandler
    import time
    try:                                           # 4.0: platforms.logs_dir()
        from peterpiper.platforms import logs_dir
        folder = logs_dir()
    except Exception:                                              # noqa: BLE001
        folder = Path.home() / "PeterPiper data" / "logs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("PeterPiper %Y-%m-%d %H-%M-%S.txt")
        log = open(path, "w", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stderr = log
    faulthandler.enable(log)

    def tidy():
        try:
            log.flush()
            empty = path.stat().st_size == 0
            log.close()
            if empty:
                path.unlink()
        except OSError:
            pass
    atexit.register(tidy)


if __name__ == "__main__":
    # 4.0: the tracker's worker processes are started with 'spawn' - a packaged app
    # must let them start (freeze_support first, before anything else)
    import multiprocessing
    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        from peterpiper import manual as _manual
        _manual.PROCS_WHEN_FROZEN = True
    if "--selftest" in sys.argv:
        from peterpiper.selftest import main as selftest
        i = sys.argv.index("--selftest")
        raise SystemExit(selftest(sys.argv[i + 1:i + 3]))
    if getattr(sys, "frozen", False):         # the packaged app: no console
        _app_log()
    from peterpiper.app import main
    raise SystemExit(main())
