"""Tests for the Pyroscope API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from cos_testing.api.pyroscope import Pyroscope

BASE_URL = "http://pyroscope:4040"


@pytest.fixture()
def pyroscope() -> Pyroscope:
    """Return a Pyroscope client with retries disabled."""
    client = Pyroscope(url=BASE_URL)
    for method_name in ("render", "get_profile_types", "get_labels", "get_label_values"):
        getattr(client, method_name).retry.wait = wait_none()
        getattr(client, method_name).retry.stop = lambda *a, **kw: True
    client.session = MagicMock(spec=requests.Session)
    return client


def _mock_response(json_data: dict | list, status_code: int = 200) -> MagicMock:
    """Create a mock ``requests.Response``."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Construction / headers
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_headers_not_set(self):
        client = Pyroscope(url=BASE_URL)
        assert client.url == BASE_URL
        assert client.headers is None
        assert isinstance(client.session, requests.Session)

    def test_custom_headers_applied(self):
        headers = {"Authorization": "Bearer tok", "X-Scope-OrgID": "tenant-1"}
        client = Pyroscope(url=BASE_URL, headers=headers)
        for key, value in headers.items():
            assert client.session.headers[key] == value

    def test_default_timeout(self):
        client = Pyroscope(url=BASE_URL)
        assert client.timeout == 60

    def test_custom_timeout(self):
        client = Pyroscope(url=BASE_URL, timeout=90)
        assert client.timeout == 90
        for method_name in ("render", "get_profile_types", "get_labels", "get_label_values"):
            stop = getattr(client, method_name).retry.stop
            assert stop.max_delay == 90


# ---------------------------------------------------------------------------
# HTTP methods – endpoint & parameter verification
# ---------------------------------------------------------------------------


class TestRender:
    def test_calls_correct_endpoint(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"flamebearer": {}, "metadata": {}})
        pyroscope.render("process_cpu:cpu:nanoseconds:cpu:nanoseconds{}")
        pyroscope.session.get.assert_called_once_with(
            f"{BASE_URL}/pyroscope/render",
            params={
                "query": "process_cpu:cpu:nanoseconds:cpu:nanoseconds{}",
                "format": "json",
            },
        )

    def test_with_start_and_end(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"flamebearer": {}})
        pyroscope.render(
            "process_cpu:cpu:nanoseconds:cpu:nanoseconds{}", start="now-1h", end="now"
        )
        _, kwargs = pyroscope.session.get.call_args
        assert kwargs["params"]["from"] == "now-1h"
        assert kwargs["params"]["until"] == "now"

    def test_with_only_start(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"flamebearer": {}})
        pyroscope.render("query{}", start="1700000000")
        _, kwargs = pyroscope.session.get.call_args
        assert kwargs["params"]["from"] == "1700000000"
        assert "until" not in kwargs["params"]

    def test_with_only_end(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"flamebearer": {}})
        pyroscope.render("query{}", end="1700003600")
        _, kwargs = pyroscope.session.get.call_args
        assert kwargs["params"]["until"] == "1700003600"
        assert "from" not in kwargs["params"]

    def test_returns_parsed_json(self, pyroscope: Pyroscope):
        payload = {
            "flamebearer": {"names": ["total", "main"], "numTicks": 100},
            "metadata": {"format": "single"},
        }
        pyroscope.session.get.return_value = _mock_response(payload)
        assert pyroscope.render("query{}") == payload

    def test_raise_for_status_called(self, pyroscope: Pyroscope):
        resp = _mock_response({})
        pyroscope.session.get.return_value = resp
        pyroscope.render("query{}")
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, pyroscope: Pyroscope):
        resp = _mock_response({}, status_code=400)
        resp.raise_for_status.side_effect = requests.HTTPError("400 Bad Request")
        pyroscope.session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            pyroscope.render("bad{}")


class TestGetProfileTypes:
    def test_calls_correct_endpoint(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({"profileTypes": []})
        pyroscope.get_profile_types()
        pyroscope.session.post.assert_called_once_with(
            f"{BASE_URL}/querier.v1.QuerierService/ProfileTypes",
            json={},
            headers={"Content-Type": "application/json"},
        )

    def test_returns_parsed_json(self, pyroscope: Pyroscope):
        payload = {
            "profileTypes": [
                {"id": "process_cpu:cpu:nanoseconds:cpu:nanoseconds", "name": "cpu"},
                {"id": "memory:alloc_objects:count:space:bytes", "name": "memory"},
            ]
        }
        pyroscope.session.post.return_value = _mock_response(payload)
        assert pyroscope.get_profile_types() == payload

    def test_raise_for_status_called(self, pyroscope: Pyroscope):
        resp = _mock_response({"profileTypes": []})
        pyroscope.session.post.return_value = resp
        pyroscope.get_profile_types()
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, pyroscope: Pyroscope):
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        pyroscope.session.post.return_value = resp
        with pytest.raises(requests.HTTPError):
            pyroscope.get_profile_types()


class TestGetLabels:
    def test_calls_correct_endpoint(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({"names": []})
        pyroscope.get_labels()
        pyroscope.session.post.assert_called_once_with(
            f"{BASE_URL}/querier.v1.QuerierService/LabelNames",
            json={},
            headers={"Content-Type": "application/json"},
        )

    def test_returns_parsed_json(self, pyroscope: Pyroscope):
        payload = {"names": ["__name__", "service_name", "instance"]}
        pyroscope.session.post.return_value = _mock_response(payload)
        assert pyroscope.get_labels() == payload

    def test_raise_for_status_called(self, pyroscope: Pyroscope):
        resp = _mock_response({"names": []})
        pyroscope.session.post.return_value = resp
        pyroscope.get_labels()
        resp.raise_for_status.assert_called_once()


class TestGetLabelValues:
    def test_calls_correct_endpoint(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(["val1", "val2"])
        pyroscope.get_label_values("service_name")
        pyroscope.session.get.assert_called_once_with(
            f"{BASE_URL}/pyroscope/label-values",
            params={"label": "service_name"},
        )

    def test_returns_parsed_json(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(["myapp", "frontend", "backend"])
        assert pyroscope.get_label_values("service_name") == ["myapp", "frontend", "backend"]

    def test_raise_for_status_called(self, pyroscope: Pyroscope):
        resp = _mock_response([])
        pyroscope.session.get.return_value = resp
        pyroscope.get_label_values("service_name")
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, pyroscope: Pyroscope):
        resp = _mock_response([], status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        pyroscope.session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            pyroscope.get_label_values("service_name")


# ---------------------------------------------------------------------------
# Check methods – has_profile
# ---------------------------------------------------------------------------


class TestHasProfile:
    def test_returns_true_when_data_exists(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(
            {"flamebearer": {"names": ["total", "main"], "numTicks": 100}}
        )
        assert pyroscope.has_profile("process_cpu:cpu:nanoseconds:cpu:nanoseconds{}") is True

    def test_returns_false_when_no_data(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(
            {"flamebearer": {"names": [], "numTicks": 0}}
        )
        assert pyroscope.has_profile("process_cpu:cpu:nanoseconds:cpu:nanoseconds{}") is False

    def test_returns_false_when_flamebearer_missing(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({})
        assert pyroscope.has_profile("query{}") is False

    def test_returns_false_when_numticks_missing(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"flamebearer": {}})
        assert pyroscope.has_profile("query{}") is False


# ---------------------------------------------------------------------------
# Check methods – has_profile_type
# ---------------------------------------------------------------------------


class TestHasProfileType:
    _profile_types_payload = {
        "profileTypes": [
            {"id": "process_cpu:cpu:nanoseconds:cpu:nanoseconds", "name": "cpu"},
            {"id": "memory:alloc_objects:count:space:bytes", "name": "memory"},
        ]
    }

    def test_returns_true_when_type_exists(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response(self._profile_types_payload)
        assert pyroscope.has_profile_type("process_cpu:cpu:nanoseconds:cpu:nanoseconds") is True

    def test_returns_false_when_type_missing(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response(self._profile_types_payload)
        assert pyroscope.has_profile_type("nonexistent:type") is False

    def test_returns_false_when_empty_list(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({"profileTypes": []})
        assert pyroscope.has_profile_type("process_cpu:cpu:nanoseconds:cpu:nanoseconds") is False

    def test_returns_false_when_key_missing(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({})
        assert pyroscope.has_profile_type("process_cpu:cpu:nanoseconds:cpu:nanoseconds") is False


# ---------------------------------------------------------------------------
# Check methods – has_label
# ---------------------------------------------------------------------------


class TestHasLabel:
    def test_label_present(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response(
            {"names": ["__name__", "service_name", "instance"]}
        )
        assert pyroscope.has_label("service_name") is True

    def test_label_absent(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response(
            {"names": ["__name__", "service_name"]}
        )
        assert pyroscope.has_label("nonexistent") is False

    def test_empty_names(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({"names": []})
        assert pyroscope.has_label("service_name") is False

    def test_missing_names_key(self, pyroscope: Pyroscope):
        pyroscope.session.post.return_value = _mock_response({})
        assert pyroscope.has_label("service_name") is False


# ---------------------------------------------------------------------------
# Check methods – has_label_value
# ---------------------------------------------------------------------------


class TestHasLabelValue:
    def test_value_present(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(["myapp", "frontend", "backend"])
        assert pyroscope.has_label_value("service_name", "myapp") is True

    def test_value_absent(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response(["myapp", "frontend"])
        assert pyroscope.has_label_value("service_name", "nonexistent") is False

    def test_empty_values(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response([])
        assert pyroscope.has_label_value("service_name", "myapp") is False

    def test_non_list_response(self, pyroscope: Pyroscope):
        pyroscope.session.get.return_value = _mock_response({"error": "unexpected"})
        assert pyroscope.has_label_value("service_name", "myapp") is False
