"""Tests for the Loki API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from cos_testing.api.loki import Loki

BASE_URL = "http://loki:3100"


@pytest.fixture()
def loki():
    """Return a Loki client with retries disabled."""
    client = Loki(url=BASE_URL)
    for method_name in ("query", "query_range", "get_labels", "get_label_values", "get_rules"):
        getattr(client, method_name).retry.wait = wait_none()
        getattr(client, method_name).retry.stop = lambda *a, **kw: True
    client.session = MagicMock()
    return client


@pytest.fixture()
def mock_get(loki):
    """Patch session.get on the Loki instance and return the mock."""
    mock = loki.session.get
    return mock


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


# ------------------------------------------------------------------
# Construction / headers
# ------------------------------------------------------------------


class TestInit:
    def test_default_headers(self):
        client = Loki(url=BASE_URL)
        assert client.url == BASE_URL
        assert client.headers is None
        assert isinstance(client.session, requests.Session)

    def test_custom_headers_applied(self):
        headers = {"X-Scope-OrgID": "tenant-1", "Authorization": "Bearer tok"}
        client = Loki(url=BASE_URL, headers=headers)
        for key, value in headers.items():
            assert client.session.headers[key] == value

    def test_default_timeout(self):
        client = Loki(url=BASE_URL)
        assert client.timeout == 60

    def test_custom_timeout(self):
        client = Loki(url=BASE_URL, timeout=30)
        assert client.timeout == 30
        for method_name in ("query", "query_range", "get_labels", "get_label_values", "get_rules"):
            stop = getattr(client, method_name).retry.stop
            assert stop.max_delay == 30


# ------------------------------------------------------------------
# HTTP methods
# ------------------------------------------------------------------


class TestQuery:
    def test_query(self, loki, mock_get):
        payload = {"data": {"result": [{"values": [["1", "line"]]}]}}
        mock_get.return_value = _json_response(payload)

        result = loki.query('{app="foo"}')

        mock_get.assert_called_once_with(
            f"{BASE_URL}/loki/api/v1/query",
            params={"query": '{app="foo"}'},
        )
        assert result == payload

    def test_query_raises_on_http_error(self, loki, mock_get):
        resp = _json_response({}, status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = resp

        with pytest.raises(requests.HTTPError):
            loki.query("bad")


class TestQueryRange:
    def test_minimal_params(self, loki, mock_get):
        payload = {"data": {"result": []}}
        mock_get.return_value = _json_response(payload)

        result = loki.query_range('{job="bar"}')

        mock_get.assert_called_once_with(
            f"{BASE_URL}/loki/api/v1/query_range",
            params={"query": '{job="bar"}', "limit": 100},
        )
        assert result == payload

    def test_with_start_and_end(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"result": []}})

        loki.query_range('{job="x"}', start="1000", end="2000", limit=50)

        mock_get.assert_called_once_with(
            f"{BASE_URL}/loki/api/v1/query_range",
            params={"query": '{job="x"}', "limit": 50, "start": "1000", "end": "2000"},
        )

    def test_with_only_start(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"result": []}})

        loki.query_range('{job="x"}', start="1000")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["start"] == "1000"
        assert "end" not in kwargs["params"]

    def test_with_only_end(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"result": []}})

        loki.query_range('{job="x"}', end="2000")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["end"] == "2000"
        assert "start" not in kwargs["params"]


class TestGetLabels:
    def test_get_labels(self, loki, mock_get):
        payload = {"data": ["job", "instance"]}
        mock_get.return_value = _json_response(payload)

        result = loki.get_labels()

        mock_get.assert_called_once_with(f"{BASE_URL}/loki/api/v1/labels")
        assert result == payload


class TestGetLabelValues:
    def test_get_label_values(self, loki, mock_get):
        payload = {"data": ["val1", "val2"]}
        mock_get.return_value = _json_response(payload)

        result = loki.get_label_values("job")

        mock_get.assert_called_once_with(f"{BASE_URL}/loki/api/v1/label/job/values")
        assert result == payload


class TestGetRules:
    def test_get_rules(self, loki, mock_get):
        payload = {"data": {"groups": [{"name": "g1", "rules": []}]}}
        mock_get.return_value = _json_response(payload)

        result = loki.get_rules()

        mock_get.assert_called_once_with(f"{BASE_URL}/loki/api/v1/rules")
        assert result == payload


# ------------------------------------------------------------------
# Check / boolean methods
# ------------------------------------------------------------------


class TestHasLogLine:
    def test_returns_true_when_entries_exist_no_pattern(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"result": [{"values": [["1", "some log line"]]}]}}
        )
        assert loki.has_log_line('{app="x"}') is True

    def test_returns_false_when_no_entries(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"result": []}})
        assert loki.has_log_line('{app="x"}') is False

    def test_pattern_matches(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"result": [{"values": [["1", "error: connection refused"]]}]}}
        )
        assert loki.has_log_line('{app="x"}', pattern=r"error:\s+connection") is True

    def test_pattern_does_not_match(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"result": [{"values": [["1", "all good"]]}]}}
        )
        assert loki.has_log_line('{app="x"}', pattern=r"error") is False

    def test_pattern_matches_across_streams(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "result": [
                        {"values": [["1", "no match here"]]},
                        {"values": [["2", "found ERROR 42"]]},
                    ]
                }
            }
        )
        assert loki.has_log_line('{app="x"}', pattern=r"ERROR \d+") is True

    def test_empty_data_key(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {}})
        assert loki.has_log_line('{app="x"}') is False

    def test_missing_data_key(self, loki, mock_get):
        mock_get.return_value = _json_response({})
        assert loki.has_log_line('{app="x"}') is False


class TestHasLabel:
    def test_label_present(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": ["job", "instance"]})
        assert loki.has_label("job") is True

    def test_label_absent(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": ["job", "instance"]})
        assert loki.has_label("missing") is False

    def test_empty_data(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": []})
        assert loki.has_label("job") is False


class TestHasLabelValue:
    def test_value_present(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": ["val1", "val2"]})
        assert loki.has_label_value("job", "val1") is True

    def test_value_absent(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": ["val1", "val2"]})
        assert loki.has_label_value("job", "val3") is False

    def test_empty_data(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": []})
        assert loki.has_label_value("job", "val1") is False


class TestHasAlertRule:
    """Test both Prometheus-style and namespace-keyed rule formats."""

    # -- Prometheus-style (data.groups is a list) --

    def test_rule_found_by_name(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"groups": [{"name": "g1", "rules": [{"name": "HighErrorRate"}]}]}}
        )
        assert loki.has_alert_rule("HighErrorRate") is True

    def test_rule_found_by_alert_field(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"groups": [{"name": "g1", "rules": [{"alert": "HighErrorRate"}]}]}}
        )
        assert loki.has_alert_rule("HighErrorRate") is True

    def test_rule_not_found(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"groups": [{"name": "g1", "rules": [{"name": "Other"}]}]}}
        )
        assert loki.has_alert_rule("HighErrorRate") is False

    def test_filter_by_group(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "groups": [
                        {"name": "g1", "rules": [{"name": "HighErrorRate"}]},
                        {"name": "g2", "rules": [{"name": "HighErrorRate"}]},
                    ]
                }
            }
        )
        assert loki.has_alert_rule("HighErrorRate", group="g2") is True
        assert loki.has_alert_rule("HighErrorRate", group="g3") is False

    def test_empty_groups(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"groups": []}})
        assert loki.has_alert_rule("HighErrorRate") is False

    # -- Namespace-keyed format (fallback) --

    def test_namespace_keyed_format(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "ns-a": [{"name": "grp1", "rules": [{"name": "DiskFull"}]}],
                    "ns-b": [{"name": "grp2", "rules": [{"alert": "MemHigh"}]}],
                }
            }
        )
        assert loki.has_alert_rule("DiskFull") is True
        assert loki.has_alert_rule("MemHigh") is True
        assert loki.has_alert_rule("Missing") is False

    def test_namespace_keyed_with_group_filter(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "ns-a": [
                        {"name": "grp1", "rules": [{"name": "DiskFull"}]},
                        {"name": "grp2", "rules": [{"name": "DiskFull"}]},
                    ],
                }
            }
        )
        assert loki.has_alert_rule("DiskFull", group="grp2") is True
        assert loki.has_alert_rule("DiskFull", group="grp99") is False

    def test_namespace_keyed_ignores_non_list_values(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "status": "success",  # not a list — should be skipped
                    "ns-a": [{"name": "grp1", "rules": [{"name": "MyRule"}]}],
                }
            }
        )
        assert loki.has_alert_rule("MyRule") is True

    def test_completely_empty_data(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {}})
        assert loki.has_alert_rule("Anything") is False


# ── has_alert_rules ──────────────────────────────────────────────────────────


class TestHasAlertRules:
    """Test label-based alert rule matching in both response formats."""

    def test_matches_single_label(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "groups": [
                        {
                            "name": "g1",
                            "rules": [
                                {"name": "HighErr", "labels": {"severity": "critical"}},
                            ],
                        }
                    ]
                }
            }
        )
        assert loki.has_alert_rules({"severity": "critical"}) is True

    def test_matches_multiple_labels(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "groups": [
                        {
                            "name": "g1",
                            "rules": [
                                {
                                    "name": "HighErr",
                                    "labels": {"severity": "critical", "team": "infra"},
                                },
                            ],
                        }
                    ]
                }
            }
        )
        assert loki.has_alert_rules({"severity": "critical", "team": "infra"}) is True

    def test_partial_label_match_fails(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "groups": [
                        {
                            "name": "g1",
                            "rules": [
                                {
                                    "name": "HighErr",
                                    "labels": {"severity": "critical", "team": "infra"},
                                },
                            ],
                        }
                    ]
                }
            }
        )
        assert loki.has_alert_rules({"severity": "critical", "team": "storage"}) is False

    def test_no_matching_label(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "groups": [
                        {
                            "name": "g1",
                            "rules": [{"name": "R", "labels": {"a": "b"}}],
                        }
                    ]
                }
            }
        )
        assert loki.has_alert_rules({"env": "prod"}) is False

    def test_rule_without_labels_key(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {"data": {"groups": [{"name": "g1", "rules": [{"name": "NoLabels"}]}]}}
        )
        assert loki.has_alert_rules({"severity": "critical"}) is False

    def test_empty_groups(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {"groups": []}})
        assert loki.has_alert_rules({"severity": "critical"}) is False

    def test_missing_data_key(self, loki, mock_get):
        mock_get.return_value = _json_response({})
        assert loki.has_alert_rules({"severity": "critical"}) is False

    # -- Namespace-keyed format (fallback) --

    def test_namespace_keyed_format(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "ns-a": [
                        {
                            "name": "grp1",
                            "rules": [
                                {"name": "DiskFull", "labels": {"team": "storage"}},
                            ],
                        }
                    ],
                }
            }
        )
        assert loki.has_alert_rules({"team": "storage"}) is True
        assert loki.has_alert_rules({"team": "infra"}) is False

    def test_namespace_keyed_ignores_non_list_values(self, loki, mock_get):
        mock_get.return_value = _json_response(
            {
                "data": {
                    "status": "success",
                    "ns-a": [
                        {
                            "name": "grp1",
                            "rules": [{"name": "R", "labels": {"a": "b"}}],
                        }
                    ],
                }
            }
        )
        assert loki.has_alert_rules({"a": "b"}) is True

    def test_completely_empty_data(self, loki, mock_get):
        mock_get.return_value = _json_response({"data": {}})
        assert loki.has_alert_rules({"severity": "critical"}) is False
