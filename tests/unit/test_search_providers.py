from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

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


def test_encrypted_provider_key_is_plaintext_only_in_runtime_plan(tmp_path, monkeypatch):
    from comicarr import config as config_module
    from comicarr import encrypted as encrypted_module

    secure_dir = tmp_path / "secure"
    secure_dir.mkdir()
    monkeypatch.setattr(encrypted_module, "_fernet_instance", None)
    secret = "runtime-provider-secret"
    token = encrypted_module.Encryptor(secret, secure_dir=str(secure_dir)).encrypt_it()["password"]
    runtime_config = config_module.Config(str(tmp_path / "config.ini"))
    runtime_config.CONFIG_VERSION = 15
    runtime_config.SECURE_DIR = str(secure_dir)
    runtime_config.ENCRYPT_PASSWORDS = True
    runtime_config.EXTRA_NEWZNABS = []
    runtime_config.EXTRA_TORZNABS = [("Nyaa", "https://indexer.test", "1", token, "5070", "1", 101)]
    monkeypatch.setattr(comicarr, "CONFIG", runtime_config)

    runtime_config._load_provider_extra_credentials()
    plan = effective_provider_plan(_config(EXTRA_TORZNABS=runtime_config.EXTRA_TORZNABS))

    candidate = next(provider for provider in plan if provider.kind == "torznab")
    assert candidate.entry[3] == secret
    assert token not in repr(candidate)
    assert secret not in repr(candidate)


@pytest.mark.parametrize("provider_count", (1, 2))
def test_provider_search_exception_logs_redact_credentials(provider_count, monkeypatch):
    secret = "provider-exception-secret"
    messages = []
    executor = ThreadPoolExecutor(max_workers=2)

    def fail_search(_scenario):
        raise RuntimeError(f"request failed https://indexer.test/api?apikey={secret}")

    monkeypatch.setattr(search, "search_the_matrix", fail_search)
    monkeypatch.setattr(search, "get_search_executor", lambda: executor)

    def submit_background_future(executor, target, *, args=(), kwargs=None, name=None):
        return executor.submit(target, *args, **(kwargs or {}))

    # Main now routes provider work through the shutdown-owned registry. Keep
    # this unit test focused on redaction by injecting its local executor.
    monkeypatch.setattr(search, "submit_background_future", submit_background_future, raising=False)
    monkeypatch.setattr(
        search.logger, "warn", lambda message, *args: messages.append(message % args if args else message)
    )
    try:
        assert search.parallel_search_providers([{} for _ in range(provider_count)]) == {"status": False}
    finally:
        executor.shutdown(wait=True)

    rendered = "\n".join(messages)
    assert secret not in rendered
    assert "[redacted]" in rendered.lower()


def test_newznab_r_query_secret_is_redacted():
    message = search.redact_sensitive_text("https://indexer.test/api?r=newznab-r-secret")

    assert "newznab-r-secret" not in message
    assert "r=[redacted]" in message


def test_rss_result_log_summary_omits_provider_signed_link():
    secret = "rss-signed-link-secret"
    result = {
        "site": "Indexer",
        "title": "Example Comic",
        "link": f"https://indexer.test/download?token={secret}",
    }

    summary = search._rss_result_log_summary(result)

    assert summary == "rss result: site=Indexer title=Example Comic"
    assert secret not in summary
    assert "indexer.test" not in summary
