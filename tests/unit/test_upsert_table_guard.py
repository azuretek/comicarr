#  Tests for scripts/check_upsert_tables.py — the literal-table-name gate (#561).
#
#  db.upsert() resolves its table by dict lookup, so "Issues" for "issues" fails
#  only at runtime, on the write path. These tests pin both halves of the gate:
#  the tree is clean today, and a mis-cased literal is actually caught.

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_upsert_tables.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("check_upsert_tables", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_every_literal_upsert_table_in_tree_is_known(guard):
    """The repository is clean — this is the regression gate for #561 itself."""
    assert guard.main() == 0


def test_table_map_keys_are_all_lowercase(guard):
    """The convention the guard's suggestion text leans on."""
    keys = guard._table_map_keys()
    assert keys, "TABLE_MAP parsed empty — the AST extraction has drifted"
    assert all(key == key.lower() for key in keys)


@pytest.mark.parametrize(
    "source",
    [
        'db.upsert("Issues", values, controls)',
        'upsert("Comics", values, controls)',
        'db.upsert_conn(conn, "Annuals", values, controls)',
    ],
)
def test_miscased_literal_is_rejected(guard, tmp_path, monkeypatch, source):
    module = tmp_path / "comicarr" / "leaf.py"
    module.parent.mkdir(parents=True)
    module.write_text(source + "\n")

    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "SCAN_GLOBS", ("comicarr/**/*.py",))

    assert guard.main() == 1


@pytest.mark.parametrize(
    "source",
    [
        'db.upsert("issues", values, controls)',
        'db.upsert_conn(conn, "provider_searches", values, controls)',
        # Runtime-built names cannot be checked statically and must not trip it.
        "db.upsert(updatetable, values, controls)",
        # Unrelated calls that merely share an argument shape.
        'mock_db.upsert.assert_any_call("Issues", values, controls)',
    ],
)
def test_valid_or_unresolvable_literal_is_accepted(guard, tmp_path, monkeypatch, source):
    module = tmp_path / "comicarr" / "leaf.py"
    module.parent.mkdir(parents=True)
    module.write_text(source + "\n")

    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "SCAN_GLOBS", ("comicarr/**/*.py",))

    assert guard.main() == 0
