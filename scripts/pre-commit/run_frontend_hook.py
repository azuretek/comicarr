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

"""Run frontend prettier/eslint from frontend/ with paths relative to that package.

Used by local pre-commit hooks so tooling resolves the frontend lockfile,
eslint config, and prettier version correctly on Windows and Unix.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "usage: run_frontend_hook.py <prettier|eslint> [files...]",
            file=sys.stderr,
        )
        return 2

    tool = args[0]
    files = args[1:]
    root = Path(__file__).resolve().parents[2]
    frontend = root / "frontend"
    node_modules = frontend / "node_modules"

    if not node_modules.is_dir():
        print(
            "frontend/node_modules missing; run: cd frontend && npm ci",
            file=sys.stderr,
        )
        return 1

    rel_files: list[str] = []
    frontend_resolved = frontend.resolve()
    for raw in files:
        path = Path(raw).resolve()
        try:
            rel = path.relative_to(frontend_resolved)
        except ValueError:
            continue
        rel_files.append(rel.as_posix())

    if files and not rel_files:
        return 0

    if tool == "prettier":
        cmd = ["npx", "prettier", "--write", "--ignore-unknown", *rel_files]
    elif tool == "eslint":
        # Match CI (`npm run lint` → `eslint .`) when no filenames are provided.
        targets = rel_files if rel_files else ["."]
        cmd = ["npx", "eslint", "--fix", *targets]
    else:
        print(f"unknown tool: {tool}", file=sys.stderr)
        return 2

    # On Windows, npx is a .cmd shim and requires shell=True.
    completed = subprocess.run(cmd, cwd=frontend, shell=(sys.platform == "win32"))
    return int(completed.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
