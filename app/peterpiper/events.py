"""
A tiny in-process event hub (PeterPiper 1.1), so optional parts (hidden extras,
the movie queue, cloud back-ups) can follow what happens in the analysis window
without the window knowing about them. A listener that fails is ignored - it
can never stop or change an analysis. No network, no files.

Events emitted by the app (keyword arguments in brackets):
    main_window_ready  (window)                  the analysis window is open
    movie_opened       (nd2, window)             a movie is open in it
    roi_added          (nd2, manual, n_cells)    a cell ROI was added (manual=True: by hand)
    roi_removed        (nd2, n_cells)
    saved              (nd2, path, n_cells)      SAVE / Save ROIs now wrote a file
    exported           (nd2, folder)             an export finished
    movie_closed       (nd2)
    queue_changed      ()
    achievement        (key)                     a hidden extra was found
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List

_listeners: Dict[str, List[Callable]] = defaultdict(list)


def on(name: str, fn: Callable) -> Callable:
    if fn not in _listeners[name]:
        _listeners[name].append(fn)
    return fn


def off(name: str, fn: Callable) -> None:
    if fn in _listeners.get(name, []):
        _listeners[name].remove(fn)


def emit(name: str, **kw) -> None:
    for fn in list(_listeners.get(name, [])):
        try:
            fn(**kw)
        except Exception:                                          # noqa: BLE001
            pass


def clear() -> None:
    """Tests: forget every listener."""
    _listeners.clear()
