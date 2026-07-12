#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT_DIR / "Comicarr.py"


def test_cli_does_not_contain_a_requirements_import_preflight():
    source = CLI_PATH.read_text()

    assert "test_the_requires" not in source
    assert "importlib.import_module" not in source


def test_cli_help_runs_without_starting_the_application():
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--help"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Automated Comic Book Downloader" in result.stdout
