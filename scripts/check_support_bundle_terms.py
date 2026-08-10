#!/usr/bin/env python3
#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Reject user-facing CarePackage language outside the versioned allowlist."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "support_bundle_legacy_terms_allowlist.txt"

# User-facing / documentation surfaces and source trees.
SCAN_GLOBS = (
    ".github/**/*",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "README.md",
    "CONTEXT.md",
    "docs/**/*",
    "frontend/src/**/*",
    "comicarr/**/*",
    "tests/**/*",
    "scripts/**/*",
)

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    "comicarr.egg-info",
    "test-results",
    "playwright-report",
}

PATTERNS = (
    re.compile(r"CarePackage"),
    re.compile(r"Care Package"),
    re.compile(r"\bcare package\b", re.IGNORECASE),
)


def load_allowlist() -> set[tuple[str, str]]:
    entries: set[tuple[str, str]] = set()
    for raw in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise SystemExit(f"invalid allowlist entry: {raw!r}")
        path, match = line.split("|", 1)
        entries.add((path, match))
    return entries


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        # Limit to text-ish extensions and known docs.
        if path.suffix.lower() not in {
            "",
            ".md",
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".mjs",
            ".json",
            ".txt",
            ".yml",
            ".yaml",
            ".toml",
            ".ini",
            ".sample",
        } and path.name not in {"bug_report.md"}:
            # Still scan known issue templates without extension tricks.
            if ".github" not in rel.parts:
                continue
        yield rel, path


def main() -> int:
    allowlist = load_allowlist()
    failures: list[str] = []
    for rel, path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel_s = rel.as_posix()
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                token = match.group(0)
                # Allow exact allowlisted path|substring pairs only.
                if (rel_s, token) in allowlist:
                    continue
                # Also allow if a longer allowlisted substring covers the token
                # on this path (e.g. carePackage vs CarePackage).
                if any(
                    path_key == rel_s and token in allowed
                    for path_key, allowed in allowlist
                ):
                    continue
                # Line context for triage.
                line_no = text.count("\n", 0, match.start()) + 1
                failures.append(f"{rel_s}:{line_no}: disallowed term {token!r}")

    if failures:
        print("Support bundle terminology guard failed:", file=sys.stderr)
        for item in failures[:50]:
            print(f"  {item}", file=sys.stderr)
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more", file=sys.stderr)
        return 1
    print("Support bundle terminology guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
