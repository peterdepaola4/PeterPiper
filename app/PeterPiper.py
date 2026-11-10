"""
Double-clickable launcher for PeterPiper (Windows).

The PeterPiper .bat file calls this file with the private virtual environment's
Python. It can also be run directly with any Python that has the packages in
requirements.txt installed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from peterpiper.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
