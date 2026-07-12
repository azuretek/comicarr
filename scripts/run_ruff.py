#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Comicarr is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Comicarr.  If not, see <http://www.gnu.org/licenses/>.

"""Invoke project ruff from .venv, PATH, or uv.

Used by root package.json lint scripts so they work without requiring
a globally installed ``uv`` on PATH (common on Windows agent setups).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Keep the modern-layer ratchet in one place. Package scripts, hooks, and CI
# all invoke ``python scripts/run_ruff.py modern`` so their target scope and
# rule selection cannot drift independently.
MODERN_TARGETS = ("comicarr/app", "Comicarr.py")
MODERN_RULES = ("E722", "F821", "F823", "B904")


def _ruff_command() -> list[str]:
    win = sys.platform == "win32"
    venv_ruff = ROOT / ".venv" / ("Scripts" if win else "bin") / ("ruff.exe" if win else "ruff")
    if venv_ruff.is_file():
        return [str(venv_ruff)]

    path_ruff = shutil.which("ruff")
    if path_ruff:
        return [path_ruff]

    path_uv = shutil.which("uv")
    if path_uv:
        return [path_uv, "run", "ruff"]

    try:
        subprocess.run(
            [sys.executable, "-m", "uv", "--version"],
            check=True,
            capture_output=True,
        )
        return [sys.executable, "-m", "uv", "run", "ruff"]
    except (OSError, subprocess.CalledProcessError):
        pass

    raise SystemExit(
        "ruff not found. Install dev deps with: uv sync --extra dev\n"
        "(or activate .venv so ruff is on PATH)"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["modern"]:
        args = ["check", *MODERN_TARGETS, "--select", ",".join(MODERN_RULES)]
    cmd = _ruff_command() + args
    return int(subprocess.call(cmd, cwd=ROOT) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
