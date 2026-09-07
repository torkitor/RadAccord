"""RadAccord: physical consistency testing before radiomic feature reuse."""
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    if sys.argv[1:] == ["--version"]:
        print("RadAccord 1.0.0")
    else:
        software = Path(__file__).resolve().parent / "software"
        sys.path.insert(0, str(software))
        runpy.run_path(str(software / "verify_refined.py"), run_name="__main__")
