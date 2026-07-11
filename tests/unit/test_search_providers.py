from types import SimpleNamespace

import comicarr
from comicarr import search
from comicarr.app.search.providers import effective_provider_plan


def _config(**overrides):
    values = {
        "ENABLE_DDL": True,
        "ENABLE_GETCOMICS": True,
        "ENABLE_EXTERNAL_SERVER": False,
        "EXPERIMENTAL": False,
        "NEWZNAB": False,
        "EXTRA_NEWZNABS": [],
        "ENABLE_TORRENT_SEARCH": True,
        "ENABLE_32P": False,
        "ENABLE_PUBLIC": False,
        "ENABLE_TORZNAB": True,
        "EXTRA_TORZNABS": [["Nyaa.si", "https://indexer.test/api", "1", "secret", "5070", "1", 1]],
        "PROVIDER_ORDER": {"0": "DDL(GetComics)"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_effective_provider_plan_includes_enabled_torznab_missing_from_saved_order():
    plan = effective_provider_plan(_config())

    assert [(candidate.name, candidate.kind, candidate.execution_name) for candidate in plan] == [
        ("DDL(GetComics)", "ddl", "DDL(GetComics)"),
        ("Nyaa.si", "torznab", "torznab: Nyaa.si"),
    ]
    assert all("secret" not in str(candidate) for candidate in plan)


def test_provider_order_routes_enabled_torznab_even_when_provider_order_is_stale(monkeypatch):
    config = _config()
    monkeypatch.setattr(comicarr, "CONFIG", config)
    monkeypatch.setattr(search.helpers, "block_provider_check", lambda _site: False)

    result = search.provider_order(initial_run=True)

    assert result["prov_order"] == ["DDL(GetComics)", "torznab: Nyaa.si"]
    assert result["torznab_info"] == [{"provider": "torznab: Nyaa.si", "info": tuple(config.EXTRA_TORZNABS[0])}]


def test_unnamed_provider_uses_safe_display_identity_without_exposing_its_endpoint():
    config = _config(
        EXTRA_TORZNABS=[["", "https://user:secret@indexer.test/api?apikey=token", "1", "secret", "5070", "1", 1]]
    )

    plan = effective_provider_plan(config)

    torznab = next(candidate for candidate in plan if candidate.kind == "torznab")
    assert torznab.name == "Torznab 1"
    assert "secret" not in repr(torznab)
    assert "indexer.test" not in repr(torznab)


def test_unnamed_provider_uses_safe_identity_during_legacy_execution(monkeypatch):
    config = _config(
        EXTRA_TORZNABS=[["", "https://user:secret@indexer.test/api?apikey=token", "1", "secret", "5070", "1", 1]]
    )
    monkeypatch.setattr(comicarr, "CONFIG", config)
    monkeypatch.setattr(search.helpers, "block_provider_check", lambda _site: False)

    result = search.provider_order()

    assert result["torznab_info"][0]["info"][0] == "Torznab 1"
    assert result["torznab_info"][0]["info"][1] == config.EXTRA_TORZNABS[0][1]
