import runpy
from pathlib import Path

_ns = runpy.run_path(str(Path(__file__).resolve().parents[2] / "auth" / "tests" / "conftest.py"))
aws = _ns["aws"]
