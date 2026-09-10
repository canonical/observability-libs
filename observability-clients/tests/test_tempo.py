"""Tests for the Tempo API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from observability_clients.api.tempo import Tempo

BASE_URL = "http://tempo:3200"


@pytest.fixture()
def tempo() -> Tempo:
    """Return a Tempo client with retries disabled."""
    client = Tempo(url=BASE_URL)
    client._retry_wait = wait_none()
    client.session = MagicMock(spec=requests.Session)
    return client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock ``requests.Response``."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def _error_response(status_code: int = 404) -> MagicMock:
    """Create a mock response that raises HTTPError."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} Not Found")
    return resp


# ---------------------------------------------------------------------------
# Construction / headers
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_headers_not_set(self):
        client = Tempo(url=BASE_URL)
        assert client.url == BASE_URL
        assert client.headers is None
        assert isinstance(client.session, requests.Session)

    def test_custom_headers_applied(self):
        headers = {"Authorization": "Bearer tok", "X-Scope-OrgID": "tenant-1"}
        client = Tempo(url=BASE_URL, headers=headers)
        for key, value in headers.items():
            assert client.session.headers[key] == value

    def test_default_timeout(self):
        client = Tempo(url=BASE_URL)
        assert client.timeout == 60

    def test_custom_timeout(self):
        client = Tempo(url=BASE_URL, timeout=90)
        assert client.timeout == 90
        assert client._retry_stop.max_delay == 90


# ---------------------------------------------------------------------------
# HTTP methods – endpoint & parameter verification
# ---------------------------------------------------------------------------


class TestSearch:
    def test_calls_correct_endpoint(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        tempo.search('{ resource.service.name = "frontend" }')
        tempo.session.get.assert_called_once_with(
            f"{BASE_URL}/api/search",
            params={"q": '{ resource.service.name = "frontend" }', "limit": 100},
        )

    def test_with_all_params(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        tempo.search("{ status = error }", start="1700000000", end="1700003600", limit=10)
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"] == {
            "q": "{ status = error }",
            "start": "1700000000",
            "end": "1700003600",
            "limit": 10,
        }

    def test_with_only_start(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        tempo.search("{ }", start="1700000000")
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"]["start"] == "1700000000"
        assert "end" not in kwargs["params"]

    def test_with_only_end(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        tempo.search("{ }", end="1700003600")
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"]["end"] == "1700003600"
        assert "start" not in kwargs["params"]

    def test_returns_parsed_json(self, tempo: Tempo):
        payload = {"traces": [{"traceID": "abc123", "spanSets": []}]}
        tempo.session.get.return_value = _mock_response(payload)
        assert tempo.search("{ }") == payload

    def test_raise_for_status_called(self, tempo: Tempo):
        resp = _mock_response({})
        tempo.session.get.return_value = resp
        tempo.search("{ }")
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, tempo: Tempo):
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        tempo.session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            tempo.search("{ }")


class TestGetTrace:
    def test_calls_correct_endpoint(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"batches": []})
        tempo.get_trace("abc123def456")
        tempo.session.get.assert_called_once_with(f"{BASE_URL}/api/traces/abc123def456")

    def test_returns_parsed_json(self, tempo: Tempo):
        payload = {"batches": [{"resource": {}, "instrumentationLibrarySpans": []}]}
        tempo.session.get.return_value = _mock_response(payload)
        assert tempo.get_trace("abc123") == payload

    def test_raise_for_status_called(self, tempo: Tempo):
        resp = _mock_response({})
        tempo.session.get.return_value = resp
        tempo.get_trace("abc123")
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, tempo: Tempo):
        tempo.session.get.return_value = _error_response(404)
        with pytest.raises(requests.HTTPError):
            tempo.get_trace("nonexistent")


class TestGetTags:
    def test_calls_correct_endpoint(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagNames": []})
        tempo.get_tags()
        tempo.session.get.assert_called_once_with(
            f"{BASE_URL}/api/search/tags",
            params={},
        )

    def test_with_scope(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagNames": []})
        tempo.get_tags(scope="resource")
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"] == {"scope": "resource"}

    def test_returns_parsed_json(self, tempo: Tempo):
        payload = {"tagNames": [{"tagName": "service.name"}, {"tagName": "http.method"}]}
        tempo.session.get.return_value = _mock_response(payload)
        assert tempo.get_tags() == payload

    def test_raise_for_status_called(self, tempo: Tempo):
        resp = _mock_response({})
        tempo.session.get.return_value = resp
        tempo.get_tags()
        resp.raise_for_status.assert_called_once()


class TestGetTagValues:
    def test_calls_correct_endpoint(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagValues": []})
        tempo.get_tag_values("service.name")
        tempo.session.get.assert_called_once_with(
            f"{BASE_URL}/api/search/tag/service.name/values",
            params={},
        )

    def test_with_query_filter(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagValues": []})
        tempo.get_tag_values("http.method", query='{ resource.service.name = "frontend" }')
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"] == {"q": '{ resource.service.name = "frontend" }'}

    def test_returns_parsed_json(self, tempo: Tempo):
        payload = {"tagValues": [{"value": "GET"}, {"value": "POST"}]}
        tempo.session.get.return_value = _mock_response(payload)
        assert tempo.get_tag_values("http.method") == payload

    def test_raise_for_status_called(self, tempo: Tempo):
        resp = _mock_response({})
        tempo.session.get.return_value = resp
        tempo.get_tag_values("service.name")
        resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# Check methods – has_trace
# ---------------------------------------------------------------------------


class TestHasTrace:
    def test_returns_true_when_trace_exists(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"batches": [{}]})
        assert tempo.has_trace("abc123") is True

    def test_returns_false_when_trace_not_found(self, tempo: Tempo):
        tempo.session.get.return_value = _error_response(404)
        assert tempo.has_trace("nonexistent") is False

    def test_returns_false_on_other_http_error(self, tempo: Tempo):
        resp = MagicMock(spec=requests.Response)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        tempo.session.get.return_value = resp
        assert tempo.has_trace("abc123") is False


# ---------------------------------------------------------------------------
# Check methods – has_traces
# ---------------------------------------------------------------------------


class TestHasTraces:
    def test_returns_true_when_traces_found(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"traces": [{"traceID": "abc123", "spanSets": []}]}
        )
        assert tempo.has_traces('{ resource.service.name = "frontend" }') is True

    def test_returns_false_when_no_traces(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        assert tempo.has_traces('{ resource.service.name = "nonexistent" }') is False

    def test_returns_false_when_traces_key_missing(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({})
        assert tempo.has_traces("{ }") is False

    def test_query_passed_correctly(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"traces": []})
        tempo.has_traces("{ status = error }")
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"]["q"] == "{ status = error }"


# ---------------------------------------------------------------------------
# Check methods – has_tag
# ---------------------------------------------------------------------------


class TestHasTag:
    def test_tag_present(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"tagNames": [{"tagName": "service.name"}, {"tagName": "http.method"}]}
        )
        assert tempo.has_tag("service.name") is True

    def test_tag_absent(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"tagNames": [{"tagName": "service.name"}]}
        )
        assert tempo.has_tag("nonexistent") is False

    def test_empty_tag_names(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagNames": []})
        assert tempo.has_tag("service.name") is False

    def test_missing_tag_names_key(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({})
        assert tempo.has_tag("service.name") is False

    def test_with_scope(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"tagNames": [{"tagName": "service.name"}]}
        )
        assert tempo.has_tag("service.name", scope="resource") is True
        _, kwargs = tempo.session.get.call_args
        assert kwargs["params"] == {"scope": "resource"}


# ---------------------------------------------------------------------------
# Check methods – has_tag_value
# ---------------------------------------------------------------------------


class TestHasTagValue:
    def test_value_present(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"tagValues": [{"value": "GET"}, {"value": "POST"}]}
        )
        assert tempo.has_tag_value("http.method", "GET") is True

    def test_value_absent(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response(
            {"tagValues": [{"value": "GET"}, {"value": "POST"}]}
        )
        assert tempo.has_tag_value("http.method", "DELETE") is False

    def test_empty_tag_values(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({"tagValues": []})
        assert tempo.has_tag_value("http.method", "GET") is False

    def test_missing_tag_values_key(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({})
        assert tempo.has_tag_value("http.method", "GET") is False


class TestIsReady:
    def test_ready(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({}, status_code=200)
        assert tempo.is_ready() is True
        tempo.session.get.assert_called_once_with(f"{BASE_URL}/ready")

    def test_not_ready(self, tempo: Tempo):
        tempo.session.get.return_value = _mock_response({}, status_code=503)
        assert tempo.is_ready() is False

    def test_connection_error(self, tempo: Tempo):
        tempo.session.get.side_effect = requests.ConnectionError("connection refused")
        assert tempo.is_ready() is False

    def test_timeout(self, tempo: Tempo):
        tempo.session.get.side_effect = requests.Timeout("timed out")
        assert tempo.is_ready() is False
