#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import subprocess
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT_DIR = Path(__file__).resolve().parents[2]
EXPORT_COMMAND = ["uv", "export", "--locked", "--no-dev", "--no-hashes", "--no-emit-project"]


def _canonical_requirements(contents):
    return [
        line
        for line in contents.splitlines()
        if line and not line.startswith("#") and not line.startswith("    #")
    ]


def _locked_runtime_export():
    result = subprocess.run(
        EXPORT_COMMAND,
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return _canonical_requirements(result.stdout)


def test_requirements_txt_matches_the_locked_runtime_export():
    generated_export = _locked_runtime_export()
    requirements_txt = _canonical_requirements((ROOT_DIR / "requirements.txt").read_text())

    assert requirements_txt == generated_export


def test_project_declares_a_setuptools_build_backend():
    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text())

    assert pyproject["build-system"] == {
        "requires": ["setuptools>=61"],
        "build-backend": "setuptools.build_meta",
    }
