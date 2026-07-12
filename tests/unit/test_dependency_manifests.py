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
SETUP_UV_ACTION = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"


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


def test_delivery_paths_install_from_the_committed_uv_lock():
    workflow = (ROOT_DIR / ".github/workflows/test.yml").read_text()
    dockerfile = (ROOT_DIR / "Dockerfile").read_text()

    assert workflow.count(SETUP_UV_ACTION) == 4
    assert "uv sync --locked --extra dev" in workflow
    assert workflow.count("uv sync --locked") >= 4
    assert "COMICARR_E2E_PYTHON: ${{ github.workspace }}/.venv/bin/python" in workflow
    assert "uv lock &&" not in dockerfile
    assert "uv sync --locked --no-dev --compile-bytecode" in dockerfile
