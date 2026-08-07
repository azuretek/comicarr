#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Only a genuinely unreachable provider may be blocklisted.

Guards the defect fixed in #560: `any([errno.ETIMEDOUT, ...])` is a list of
nonzero constants and so was unconditionally true, meaning every request error
— a plain 429 included — disabled the provider and aborted the search.
"""

import errno
import socket
from types import SimpleNamespace

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from comicarr.app.search.service import provider_unreachable


def _http_error(status_code):
    response = SimpleNamespace(status_code=status_code)
    return requests.exceptions.HTTPError("%s error" % status_code, response=response)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 429, 500, 503])
def test_any_http_response_means_the_provider_is_alive(status_code):
    assert provider_unreachable(_http_error(status_code)) is False


def test_rate_limit_does_not_disable_the_provider():
    # The exact production symptom: Prowlarr 429 was blocklisting the provider.
    assert provider_unreachable(_http_error(429)) is False


@pytest.mark.parametrize(
    "code",
    [errno.ETIMEDOUT, errno.ECONNREFUSED, errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ENETUNREACH],
)
def test_socket_errnos_buried_under_urllib3_are_found(code):
    os_error = OSError(code, "boom")
    wrapped = requests.exceptions.ConnectionError(ProtocolError("Connection aborted.", os_error))

    assert provider_unreachable(wrapped) is True


def test_errno_reached_through_exception_chaining():
    try:
        try:
            raise OSError(errno.ECONNREFUSED, "refused")
        except OSError as os_error:
            raise requests.exceptions.ConnectionError("wrapped") from os_error
    except requests.exceptions.ConnectionError as e:
        assert provider_unreachable(e) is True


def test_unrelated_errno_does_not_disable_the_provider():
    os_error = OSError(errno.EACCES, "permission denied")
    wrapped = requests.exceptions.ConnectionError(ProtocolError("Connection aborted.", os_error))

    assert provider_unreachable(wrapped) is False


def test_dns_failure_with_no_errno_still_counts_as_unreachable():
    pool = SimpleNamespace(scheme="https", host="indexer.test", port=443)
    reason = NewConnectionError(pool, "Failed to resolve 'indexer.test'")
    wrapped = requests.exceptions.ConnectionError(MaxRetryError(pool, "https://indexer.test/api", reason=reason))

    assert provider_unreachable(wrapped) is True


def test_read_timeout_counts_as_unreachable():
    assert provider_unreachable(requests.exceptions.ReadTimeout("timed out")) is True


def test_socket_timeout_under_a_requests_timeout_is_unreachable():
    assert provider_unreachable(requests.exceptions.ConnectTimeout(socket.timeout("timed out"))) is True


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.TooManyRedirects("too many redirects"),
        requests.exceptions.InvalidURL("bad url"),
        requests.exceptions.ContentDecodingError("bad gzip"),
        requests.exceptions.ChunkedEncodingError("bad chunk"),
    ],
)
def test_client_side_request_errors_leave_the_provider_enabled(exc):
    assert provider_unreachable(exc) is False


def test_http_error_without_a_response_is_not_treated_as_unreachable():
    assert provider_unreachable(requests.exceptions.HTTPError("no response attached")) is False


def test_self_referential_exception_chain_terminates():
    # __context__ can point back at an ancestor; the depth cap must stop the walk.
    outer = requests.exceptions.ConnectionError("outer")
    inner = requests.exceptions.ConnectionError("inner")
    outer.__context__ = inner
    inner.__context__ = outer

    assert provider_unreachable(outer) is True
