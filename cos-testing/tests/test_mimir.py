"""Tests for the Mimir API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from cos_testing.api.mimir import Mimir

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mimir() -> Mimir:
    """Return a Mimir client with retries disabled."""
    client = Mimir(url="http://mimir:9009")
    # Disable tenacity waits so tests don't sleep on retries.
    client.query.retry.wait = wait_none()
    client.query_range.retry.wait = wait_none()
    client.get_rules.retry.wait = wait_none()
    client.get_alerts.retry.wait = wait_none()
    # Replace the real session with a mock.
    client.session = MagicMock(spec=requests.Session)
    return client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
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
        client = Mimir(url="http://mimir:9009")
        # Session should exist but no extra headers added.
        assert isinstance(client.session, requests.Session)

    def test_custom_headers_applied(self):
        headers = {"X-Scope-OrgID": "tenant-1"}
        client = Mimir(url="http://mimir:9009", headers=headers)
        assert client.session.headers["X-Scope-OrgID"] == "tenant-1"

    def test_default_timeout(self):
        client = Mimir(url="http://mimir:9009")
        assert client.timeout == 60

    def test_custom_timeout(self):
        client = Mimir(url="http://mimir:9009", timeout=90)
        assert client.timeout == 90
        for method_name in ("query", "query_range", "get_rules", "get_alerts"):
            stop = getattr(client, method_name).retry.stop
            assert stop.max_delay == 90


# ---------------------------------------------------------------------------
# HTTP methods – endpoint & parameter verification
# ---------------------------------------------------------------------------


class TestQuery:
    def test_calls_correct_endpoint(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        mimir.query("up")
        mimir.session.get.assert_called_once_with(
            "http://mimir:9009/prometheus/api/v1/query",
            params={"query": "up"},
        )

    def test_returns_parsed_json(self, mimir: Mimir):
        payload = {"status": "success", "data": {"resultType": "vector", "result": []}}
        mimir.session.get.return_value = _mock_response(payload)
        assert mimir.query("up") == payload

    def test_raise_for_status_called(self, mimir: Mimir):
        resp = _mock_response({})
        mimir.session.get.return_value = resp
        mimir.query("up")
        resp.raise_for_status.assert_called_once()

    def test_http_error_propagates(self, mimir: Mimir):
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mimir.session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            mimir.query("up")


class TestQueryRange:
    def test_calls_correct_endpoint_with_default_step(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        mimir.query_range("up", start="2024-01-01T00:00:00Z", end="2024-01-01T01:00:00Z")
        mimir.session.get.assert_called_once_with(
            "http://mimir:9009/prometheus/api/v1/query_range",
            params={
                "query": "up",
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-01T01:00:00Z",
                "step": "15s",
            },
        )

    def test_custom_step(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        mimir.query_range("up", start="0", end="1", step="1m")
        _, kwargs = mimir.session.get.call_args
        assert kwargs["params"]["step"] == "1m"

    def test_returns_parsed_json(self, mimir: Mimir):
        payload = {"status": "success", "data": {"resultType": "matrix", "result": []}}
        mimir.session.get.return_value = _mock_response(payload)
        result = mimir.query_range("up", start="0", end="1")
        assert result == payload


class TestGetRules:
    def test_calls_correct_endpoint(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"groups": []}})
        mimir.get_rules()
        mimir.session.get.assert_called_once_with(
            "http://mimir:9009/prometheus/api/v1/rules",
        )

    def test_returns_parsed_json(self, mimir: Mimir):
        payload = {"status": "success", "data": {"groups": []}}
        mimir.session.get.return_value = _mock_response(payload)
        assert mimir.get_rules() == payload


class TestGetAlerts:
    def test_calls_correct_endpoint(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"alerts": []}})
        mimir.get_alerts()
        mimir.session.get.assert_called_once_with(
            "http://mimir:9009/prometheus/api/v1/alerts",
        )

    def test_returns_parsed_json(self, mimir: Mimir):
        payload = {"status": "success", "data": {"alerts": []}}
        mimir.session.get.return_value = _mock_response(payload)
        assert mimir.get_alerts() == payload


# ---------------------------------------------------------------------------
# Check methods – has_metric
# ---------------------------------------------------------------------------


class TestHasMetric:
    def test_returns_true_when_results_present(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(
            {"data": {"result": [{"metric": {"__name__": "up"}, "value": [0, "1"]}]}}
        )
        assert mimir.has_metric("up") is True

    def test_returns_false_when_no_results(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        assert mimir.has_metric("up") is False

    def test_query_without_labels(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        mimir.has_metric("up")
        _, kwargs = mimir.session.get.call_args
        assert kwargs["params"]["query"] == "up"

    def test_query_with_labels(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"result": []}})
        mimir.has_metric("up", labels={"job": "prometheus", "instance": "localhost:9090"})
        _, kwargs = mimir.session.get.call_args
        query = kwargs["params"]["query"]
        assert query.startswith("up{")
        assert 'job="prometheus"' in query
        assert 'instance="localhost:9090"' in query

    def test_returns_false_on_empty_data(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({})
        assert mimir.has_metric("up") is False

    def test_returns_false_when_data_key_missing_result(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {}})
        assert mimir.has_metric("up") is False


# ---------------------------------------------------------------------------
# Check methods – has_alert_rule
# ---------------------------------------------------------------------------

_RULES_PAYLOAD = {
    "data": {
        "groups": [
            {
                "name": "critical",
                "rules": [
                    {"name": "HighMemory", "type": "alerting"},
                    {"name": "HighCPU", "type": "alerting"},
                    {"name": "avg_memory", "type": "recording"},
                ],
            },
            {
                "name": "warnings",
                "rules": [
                    {"name": "DiskAlmostFull", "type": "alerting"},
                ],
            },
        ]
    }
}


class TestHasAlertRule:
    def test_returns_true_for_existing_rule(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_RULES_PAYLOAD)
        assert mimir.has_alert_rule("HighMemory") is True

    def test_returns_false_for_nonexistent_rule(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_RULES_PAYLOAD)
        assert mimir.has_alert_rule("DoesNotExist") is False

    def test_ignores_recording_rules(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_RULES_PAYLOAD)
        assert mimir.has_alert_rule("avg_memory") is False

    def test_filters_by_group(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_RULES_PAYLOAD)
        assert mimir.has_alert_rule("DiskAlmostFull", group="warnings") is True

    def test_group_filter_excludes_other_groups(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_RULES_PAYLOAD)
        assert mimir.has_alert_rule("HighMemory", group="warnings") is False

    def test_returns_false_on_empty_groups(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"groups": []}})
        assert mimir.has_alert_rule("HighMemory") is False

    def test_returns_false_on_missing_data(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({})
        assert mimir.has_alert_rule("HighMemory") is False


# ---------------------------------------------------------------------------
# Check methods – has_alert_rules
# ---------------------------------------------------------------------------


class TestHasAlertRules:
    _rules_payload = {
        "data": {
            "groups": [
                {
                    "name": "critical",
                    "rules": [
                        {
                            "name": "HighMemory",
                            "type": "alerting",
                            "labels": {"severity": "critical", "team": "infra"},
                        },
                        {
                            "name": "AvgCPU",
                            "type": "recording",
                            "labels": {"severity": "warning"},
                        },
                    ],
                },
                {
                    "name": "warnings",
                    "rules": [
                        {
                            "name": "DiskAlmostFull",
                            "type": "alerting",
                            "labels": {"severity": "warning", "team": "storage"},
                        },
                    ],
                },
            ]
        }
    }

    def test_matches_single_label(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(self._rules_payload)
        assert mimir.has_alert_rules({"severity": "critical"}) is True

    def test_matches_multiple_labels(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(self._rules_payload)
        assert mimir.has_alert_rules({"severity": "critical", "team": "infra"}) is True

    def test_partial_label_match_fails(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(self._rules_payload)
        assert mimir.has_alert_rules({"severity": "critical", "team": "storage"}) is False

    def test_no_matching_label(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(self._rules_payload)
        assert mimir.has_alert_rules({"env": "production"}) is False

    def test_ignores_recording_rules(self, mimir: Mimir):
        payload = {
            "data": {
                "groups": [
                    {
                        "name": "g",
                        "rules": [
                            {"name": "Rec", "type": "recording", "labels": {"a": "b"}},
                        ],
                    }
                ]
            }
        }
        mimir.session.get.return_value = _mock_response(payload)
        assert mimir.has_alert_rules({"a": "b"}) is False

    def test_empty_groups(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"groups": []}})
        assert mimir.has_alert_rules({"severity": "critical"}) is False

    def test_missing_data_key(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({})
        assert mimir.has_alert_rules({"severity": "critical"}) is False

    def test_rule_without_labels_key(self, mimir: Mimir):
        payload = {
            "data": {
                "groups": [
                    {
                        "name": "g",
                        "rules": [{"name": "NoLabels", "type": "alerting"}],
                    }
                ]
            }
        }
        mimir.session.get.return_value = _mock_response(payload)
        assert mimir.has_alert_rules({"severity": "critical"}) is False


# ---------------------------------------------------------------------------
# Check methods – has_active_alert
# ---------------------------------------------------------------------------

_ALERTS_PAYLOAD = {
    "data": {
        "alerts": [
            {
                "labels": {"alertname": "HighMemory", "severity": "critical", "job": "node"},
                "state": "firing",
            },
            {
                "labels": {"alertname": "DiskAlmostFull", "severity": "warning"},
                "state": "firing",
            },
        ]
    }
}


class TestHasActiveAlert:
    def test_returns_true_for_active_alert(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert mimir.has_active_alert("HighMemory") is True

    def test_returns_false_for_nonexistent_alert(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert mimir.has_active_alert("DoesNotExist") is False

    def test_matches_with_labels(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert mimir.has_active_alert("HighMemory", labels={"severity": "critical"}) is True

    def test_label_mismatch_returns_false(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert mimir.has_active_alert("HighMemory", labels={"severity": "warning"}) is False

    def test_partial_label_match(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert (
            mimir.has_active_alert("HighMemory", labels={"severity": "critical", "job": "node"})
            is True
        )

    def test_extra_label_not_present_returns_false(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response(_ALERTS_PAYLOAD)
        assert mimir.has_active_alert("HighMemory", labels={"env": "prod"}) is False

    def test_returns_false_on_empty_alerts(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({"data": {"alerts": []}})
        assert mimir.has_active_alert("HighMemory") is False

    def test_returns_false_on_missing_data(self, mimir: Mimir):
        mimir.session.get.return_value = _mock_response({})
        assert mimir.has_active_alert("HighMemory") is False
