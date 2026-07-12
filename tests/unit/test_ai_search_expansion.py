#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for ``comicarr.app.ai.search_expansion``."""

import json
from unittest.mock import MagicMock, patch

from comicarr.app.ai.schemas import SearchExpansion


def _configure_available_ai(mock_get_ai_runtime):
    mock_ctx = mock_get_ai_runtime.return_value
    mock_ctx.ai_client = MagicMock()
    mock_ctx.ai_circuit_breaker = MagicMock()
    mock_ctx.ai_circuit_breaker.allow_request.return_value = True
    mock_ctx.ai_rate_limiter = MagicMock()
    mock_ctx.ai_rate_limiter.can_request.return_value = True
    mock_ctx.config = MagicMock()
    mock_ctx.config.AI_MODEL = "gpt-4"
    mock_ctx.config.AI_TIMEOUT = 30
    return mock_ctx


class TestExpandSearchQueries:
    """Test AI expansion behavior independently from the Core query layer."""

    @patch("comicarr.app.ai.search_expansion.ai_service")
    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.request_structured")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_returns_alternates_on_success(self, mock_get_ai_runtime, mock_structured, mock_queries, mock_ai_service):
        mock_ctx = _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = None
        mock_queries.get_alternate_search.return_value = None
        mock_structured.return_value = SearchExpansion(queries=["The Amazing Spider-Man", "ASM", "Spider-Man Marvel"])

        from comicarr.app.ai.search_expansion import expand_search_queries

        result = expand_search_queries("12345", "Spider-Man", publisher="Marvel", year="2020")

        assert result == ["The Amazing Spider-Man", "ASM", "Spider-Man Marvel"]
        mock_ctx.ai_circuit_breaker.record_success.assert_called_once()
        mock_ai_service.log_activity.assert_called_once()

    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_ai_not_configured_returns_empty(self, mock_get_ai_runtime):
        mock_ctx = mock_get_ai_runtime.return_value
        mock_ctx.ai_client = None

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []

    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_circuit_breaker_open_returns_empty(self, mock_get_ai_runtime):
        mock_ctx = _configure_available_ai(mock_get_ai_runtime)
        mock_ctx.ai_circuit_breaker.allow_request.return_value = False

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []

    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_already_has_five_expansions_returns_empty(self, mock_get_ai_runtime, mock_queries):
        _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = {"data": json.dumps(["alt1", "alt2", "alt3", "alt4", "alt5"])}

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []

    @patch("comicarr.app.ai.search_expansion.ai_service")
    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.request_structured")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_deduplicates_against_existing_alternates(
        self, mock_get_ai_runtime, mock_structured, mock_queries, mock_ai_service
    ):
        _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = None
        mock_queries.get_alternate_search.return_value = {"AlternateSearch": "The Dark Knight"}
        mock_structured.return_value = SearchExpansion(queries=["The Dark Knight", "TDK", "Batman Dark Knight"])

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Batman") == ["TDK", "Batman Dark Knight"]

    @patch("comicarr.app.ai.search_expansion.ai_service")
    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.request_structured")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_deduplicates_against_series_name(
        self, mock_get_ai_runtime, mock_structured, mock_queries, mock_ai_service
    ):
        _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = None
        mock_queries.get_alternate_search.return_value = None
        mock_structured.return_value = SearchExpansion(queries=["batman", "The Dark Knight"])

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Batman") == ["The Dark Knight"]

    @patch("comicarr.app.ai.search_expansion.ai_service")
    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.request_structured")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_llm_timeout_returns_empty(self, mock_get_ai_runtime, mock_structured, mock_queries, mock_ai_service):
        mock_ctx = _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = None
        mock_queries.get_alternate_search.return_value = None
        mock_structured.side_effect = TimeoutError("Request timed out")

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []
        mock_ctx.ai_circuit_breaker.record_failure.assert_called_once()

    @patch("comicarr.app.ai.search_expansion.ai_service")
    @patch("comicarr.app.ai.search_expansion.ai_queries")
    @patch("comicarr.app.ai.search_expansion.request_structured")
    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_llm_returns_empty_array(self, mock_get_ai_runtime, mock_structured, mock_queries, mock_ai_service):
        mock_ctx = _configure_available_ai(mock_get_ai_runtime)
        mock_queries.get_cache_entry.return_value = None
        mock_queries.get_alternate_search.return_value = None
        mock_structured.return_value = SearchExpansion(queries=[])

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []
        mock_ctx.ai_circuit_breaker.record_success.assert_called_once()

    @patch("comicarr.app.ai.search_expansion.get_ai_runtime")
    def test_rate_limit_reached_returns_empty(self, mock_get_ai_runtime):
        mock_ctx = _configure_available_ai(mock_get_ai_runtime)
        mock_ctx.ai_rate_limiter.can_request.return_value = False

        from comicarr.app.ai.search_expansion import expand_search_queries

        assert expand_search_queries("12345", "Spider-Man") == []


class TestPersistSuccessfulExpansion:
    """Test the query-helper calls that persist successful expansions."""

    @patch("comicarr.app.ai.search_expansion.ai_queries")
    def test_updates_alternate_search_and_cache(self, mock_queries):
        mock_queries.get_alternate_search.return_value = {"AlternateSearch": "Existing Alt"}
        mock_queries.get_cache_entry.return_value = None

        from comicarr.app.ai.search_expansion import persist_successful_expansion

        persist_successful_expansion("12345", "New Alt")

        mock_queries.update_alternate_search.assert_called_once_with("12345", "Existing Alt##New Alt")
        cache_call = mock_queries.upsert_cache_entry.call_args.args
        assert cache_call[:2] == ("expansion_12345", "expansion")
        assert json.loads(cache_call[2]) == ["New Alt"]
        assert cache_call[4] == "9999-12-31"

    @patch("comicarr.app.ai.search_expansion.ai_queries")
    def test_does_not_duplicate_existing_alternate(self, mock_queries):
        mock_queries.get_alternate_search.return_value = {"AlternateSearch": "Existing Alt"}
        mock_queries.get_cache_entry.return_value = None

        from comicarr.app.ai.search_expansion import persist_successful_expansion

        persist_successful_expansion("12345", "existing alt")

        mock_queries.update_alternate_search.assert_not_called()
        assert json.loads(mock_queries.upsert_cache_entry.call_args.args[2]) == ["existing alt"]

    @patch("comicarr.app.ai.search_expansion.ai_queries")
    def test_first_alternate_has_no_existing_value(self, mock_queries):
        mock_queries.get_alternate_search.return_value = None
        mock_queries.get_cache_entry.return_value = None

        from comicarr.app.ai.search_expansion import persist_successful_expansion

        persist_successful_expansion("12345", "New Alt")

        mock_queries.update_alternate_search.assert_called_once_with("12345", "New Alt")

    @patch("comicarr.app.ai.search_expansion.ai_queries")
    def test_appends_to_ai_cache(self, mock_queries):
        mock_queries.get_alternate_search.return_value = {"AlternateSearch": "prev alt 1##prev alt 2"}
        mock_queries.get_cache_entry.return_value = {"data": json.dumps(["prev alt 1", "prev alt 2"])}

        from comicarr.app.ai.search_expansion import persist_successful_expansion

        persist_successful_expansion("12345", "New Alt")

        assert json.loads(mock_queries.upsert_cache_entry.call_args.args[2]) == ["prev alt 1", "prev alt 2", "New Alt"]
