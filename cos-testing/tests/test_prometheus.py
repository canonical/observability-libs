"""Tests for the Prometheus API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from tenacity import wait_none

from cos_testing.api.prometheus import Prometheus


@pytest.fixture()
def prom():
    """Create a Prometheus client with retries disabled."""
    client = Prometheus(url="http://localhost:9090")
    for method_name in ("query", "query_range", "get_rules", "get_alerts", "get_targets"):
        getattr(client, method_name).retry.wait = wait_none()
        getattr(client, method_name).retry.stop = lambda *a, **kw: True
    client.session = MagicMock()
    return client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ── Initialization ───────────────────────────────────────────────────────────


class TestInit:
    def test_creates_session(self):
        client = Prometheus(url="http://localhost:9090")
        assert client.session is not None

    def test_headers_applied(self):
        client = Prometheus(url="http://prom:9090", headers={"Authorization": "Bearer tok"})
        assert client.session.headers["Authorization"] == "Bearer tok"

    def test_no_headers(self):
        client = Prometheus(url="http://prom:9090")
        # session.headers.update should not have been called with extra headers
        assert client.headers is None

    def test_default_timeout(self):
        client = Prometheus(url="http://prom:9090")
        assert client.timeout == 60

    def test_custom_timeout(self):
        client = Prometheus(url="http://prom:9090", timeout=120)
        assert client.timeout == 120
        for method_name in ("query", "query_range", "get_rules", "get_alerts", "get_targets"):
            stop = getattr(client, method_name).retry.stop
            assert stop.max_delay == 120


# ── HTTP methods ─────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_returns_json(self, prom):
        payload = {"status": "success", "data": {"resultType": "vector", "result": []}}
        prom.session.get.return_value = _mock_response(payload)

        result = prom.query("up")

        prom.session.get.assert_called_once_with(
            "http://localhost:9090/api/v1/query", params={"query": "up"}
        )
        assert result == payload

    def test_query_raises_on_http_error(self, prom):
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = Exception("500 Server Error")
        prom.session.get.return_value = resp

        with pytest.raises(Exception, match="500 Server Error"):
            prom.query("up")


class TestQueryRange:
    def test_query_range_default_step(self, prom):
        payload = {"status": "success", "data": {"resultType": "matrix", "result": []}}
        prom.session.get.return_value = _mock_response(payload)

        result = prom.query_range("up", start="2024-01-01T00:00:00Z", end="2024-01-01T01:00:00Z")

        prom.session.get.assert_called_once_with(
            "http://localhost:9090/api/v1/query_range",
            params={
                "query": "up",
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-01T01:00:00Z",
                "step": "15s",
            },
        )
        assert result == payload

    def test_query_range_custom_step(self, prom):
        prom.session.get.return_value = _mock_response({"status": "success"})

        prom.query_range("rate(up[5m])", start="0", end="3600", step="60s")

        _, kwargs = prom.session.get.call_args
        assert kwargs["params"]["step"] == "60s"

    def test_query_range_raises_on_http_error(self, prom):
        resp = _mock_response({}, status_code=400)
        resp.raise_for_status.side_effect = Exception("400 Bad Request")
        prom.session.get.return_value = resp

        with pytest.raises(Exception, match="400 Bad Request"):
            prom.query_range("bad{", start="0", end="1")


class TestGetRules:
    def test_get_rules_returns_json(self, prom):
        payload = {"status": "success", "data": {"groups": []}}
        prom.session.get.return_value = _mock_response(payload)

        result = prom.get_rules()

        prom.session.get.assert_called_once_with("http://localhost:9090/api/v1/rules")
        assert result == payload


class TestGetAlerts:
    def test_get_alerts_returns_json(self, prom):
        payload = {"status": "success", "data": {"alerts": []}}
        prom.session.get.return_value = _mock_response(payload)

        result = prom.get_alerts()

        prom.session.get.assert_called_once_with("http://localhost:9090/api/v1/alerts")
        assert result == payload


class TestGetTargets:
    def test_get_targets_returns_json(self, prom):
        payload = {"status": "success", "data": {"activeTargets": [], "droppedTargets": []}}
        prom.session.get.return_value = _mock_response(payload)

        result = prom.get_targets()

        prom.session.get.assert_called_once_with("http://localhost:9090/api/v1/targets")
        assert result == payload


# ── has_metric ───────────────────────────────────────────────────────────────


class TestHasMetric:
    def test_metric_found(self, prom):
        prom.session.get.return_value = _mock_response(
            {"data": {"result": [{"metric": {"__name__": "up"}, "value": [0, "1"]}]}}
        )
        assert prom.has_metric("up") is True

    def test_metric_not_found(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"result": []}})
        assert prom.has_metric("nonexistent") is False

    def test_metric_with_labels(self, prom):
        prom.session.get.return_value = _mock_response(
            {
                "data": {
                    "result": [{"metric": {"__name__": "up", "job": "node"}, "value": [0, "1"]}]
                }
            }
        )
        assert prom.has_metric("up", labels={"job": "node"}) is True

        _, kwargs = prom.session.get.call_args
        assert kwargs["params"]["query"] == 'up{job="node"}'

    def test_metric_with_multiple_labels(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"result": [{"value": [0, "1"]}]}})

        prom.has_metric("http_requests_total", labels={"method": "GET", "code": "200"})

        _, kwargs = prom.session.get.call_args
        query = kwargs["params"]["query"]
        assert "method=" in query
        assert "code=" in query

    def test_metric_empty_data(self, prom):
        prom.session.get.return_value = _mock_response({"data": {}})
        assert prom.has_metric("up") is False

    def test_metric_missing_data_key(self, prom):
        prom.session.get.return_value = _mock_response({})
        assert prom.has_metric("up") is False

    def test_metric_without_labels_sends_bare_name(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"result": []}})

        prom.has_metric("up")

        _, kwargs = prom.session.get.call_args
        assert kwargs["params"]["query"] == "up"

    def test_metric_labels_only(self, prom):
        prom.session.get.return_value = _mock_response(
            {"data": {"result": [{"metric": {"job": "node"}, "value": [0, "1"]}]}}
        )
        assert prom.has_metric(labels={"job": "node"}) is True

        _, kwargs = prom.session.get.call_args
        assert kwargs["params"]["query"] == '{job="node"}'

    def test_metric_labels_only_not_found(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"result": []}})
        assert prom.has_metric(labels={"job": "nonexistent"}) is False

    def test_metric_labels_only_multiple(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"result": [{"value": [0, "1"]}]}})
        prom.has_metric(labels={"job": "node", "instance": "host1"})

        _, kwargs = prom.session.get.call_args
        query = kwargs["params"]["query"]
        assert query.startswith("{")
        assert 'job="node"' in query
        assert 'instance="host1"' in query

    def test_metric_no_args_raises(self, prom):
        with pytest.raises(ValueError, match="At least one"):
            prom.has_metric()


# ── has_alert_rule ───────────────────────────────────────────────────────────


class TestHasAlertRule:
    _rules_payload = {
        "data": {
            "groups": [
                {
                    "name": "example",
                    "rules": [
                        {"name": "HighMemory", "type": "alerting"},
                        {"name": "AvgCPU", "type": "recording"},
                    ],
                },
                {
                    "name": "infra",
                    "rules": [
                        {"name": "DiskFull", "type": "alerting"},
                    ],
                },
            ]
        }
    }

    def test_rule_found(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("HighMemory") is True

    def test_rule_not_found(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("NonExistent") is False

    def test_recording_rule_not_matched(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("AvgCPU") is False

    def test_rule_found_with_group_filter(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("DiskFull", group="infra") is True

    def test_rule_not_in_specified_group(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("HighMemory", group="infra") is False

    def test_rule_with_wrong_group(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rule("DiskFull", group="nonexistent") is False

    def test_empty_groups(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"groups": []}})
        assert prom.has_alert_rule("HighMemory") is False

    def test_missing_data_key(self, prom):
        prom.session.get.return_value = _mock_response({})
        assert prom.has_alert_rule("HighMemory") is False


# ── has_alert_rules ──────────────────────────────────────────────────────────


class TestHasAlertRules:
    _rules_payload = {
        "data": {
            "groups": [
                {
                    "name": "example",
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
                    "name": "infra",
                    "rules": [
                        {
                            "name": "DiskFull",
                            "type": "alerting",
                            "labels": {"severity": "warning", "team": "storage"},
                        },
                    ],
                },
            ]
        }
    }

    def test_matches_single_label(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rules({"severity": "critical"}) is True

    def test_matches_multiple_labels(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rules({"severity": "critical", "team": "infra"}) is True

    def test_partial_label_match_fails(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rules({"severity": "critical", "team": "storage"}) is False

    def test_no_matching_label(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        assert prom.has_alert_rules({"env": "production"}) is False

    def test_ignores_recording_rules(self, prom):
        prom.session.get.return_value = _mock_response(self._rules_payload)
        # "AvgCPU" is a recording rule with severity=warning; should not match
        # when it's the only rule with that exact label set
        assert prom.has_alert_rules({"severity": "warning"}) is True  # DiskFull matches

    def test_recording_rule_only(self, prom):
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
        prom.session.get.return_value = _mock_response(payload)
        assert prom.has_alert_rules({"a": "b"}) is False

    def test_empty_groups(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"groups": []}})
        assert prom.has_alert_rules({"severity": "critical"}) is False

    def test_missing_data_key(self, prom):
        prom.session.get.return_value = _mock_response({})
        assert prom.has_alert_rules({"severity": "critical"}) is False

    def test_rule_without_labels_key(self, prom):
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
        prom.session.get.return_value = _mock_response(payload)
        assert prom.has_alert_rules({"severity": "critical"}) is False


# ── has_active_alert ─────────────────────────────────────────────────────────


class TestHasActiveAlert:
    _alerts_payload = {
        "data": {
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighMemory",
                        "severity": "critical",
                        "instance": "host1",
                    },
                    "state": "firing",
                },
                {
                    "labels": {"alertname": "DiskFull", "severity": "warning"},
                    "state": "pending",
                },
            ]
        }
    }

    def test_alert_found(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert prom.has_active_alert("HighMemory") is True

    def test_alert_not_found(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert prom.has_active_alert("NonExistent") is False

    def test_alert_with_matching_labels(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert prom.has_active_alert("HighMemory", labels={"severity": "critical"}) is True

    def test_alert_with_multiple_matching_labels(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert (
            prom.has_active_alert(
                "HighMemory", labels={"severity": "critical", "instance": "host1"}
            )
            is True
        )

    def test_alert_with_non_matching_labels(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert prom.has_active_alert("HighMemory", labels={"severity": "warning"}) is False

    def test_alert_with_partial_label_mismatch(self, prom):
        prom.session.get.return_value = _mock_response(self._alerts_payload)
        assert (
            prom.has_active_alert(
                "HighMemory", labels={"severity": "critical", "instance": "host999"}
            )
            is False
        )

    def test_empty_alerts(self, prom):
        prom.session.get.return_value = _mock_response({"data": {"alerts": []}})
        assert prom.has_active_alert("HighMemory") is False

    def test_missing_data_key(self, prom):
        prom.session.get.return_value = _mock_response({})
        assert prom.has_active_alert("HighMemory") is False


# ── has_target ───────────────────────────────────────────────────────────────


class TestHasTarget:
    _targets_payload = {
        "data": {
            "activeTargets": [
                {
                    "labels": {"job": "prometheus", "instance": "localhost:9090"},
                    "discoveredLabels": {"job": "prometheus"},
                    "scrapeUrl": "http://localhost:9090/metrics",
                    "health": "up",
                },
                {
                    "labels": {"job": "node", "instance": "localhost:9100"},
                    "discoveredLabels": {"job": "node"},
                    "scrapeUrl": "http://localhost:9100/metrics",
                    "health": "down",
                },
            ],
            "droppedTargets": [
                {
                    "labels": {},
                    "discoveredLabels": {"job": "dropped-job"},
                    "scrapeUrl": "http://localhost:1234/metrics",
                },
            ],
        }
    }

    def test_target_found_by_job(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(job="prometheus") is True

    def test_target_not_found_by_job(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(job="nonexistent") is False

    def test_target_found_by_url(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(url="http://localhost:9090/metrics") is True

    def test_target_not_found_by_url(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(url="http://unknown:9999/metrics") is False

    def test_target_found_by_health(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(health="up") is True

    def test_target_found_by_health_down(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(health="down") is True

    def test_target_not_found_by_health(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(health="unknown") is False

    def test_target_found_by_job_and_health(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(job="node", health="down") is True

    def test_target_job_health_mismatch(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(job="node", health="up") is False

    def test_target_found_by_job_url_and_health(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert (
            prom.has_target(job="prometheus", url="http://localhost:9090/metrics", health="up")
            is True
        )

    def test_dropped_target_found_by_discovered_job(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(job="dropped-job") is True

    def test_dropped_target_found_by_url(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target(url="http://localhost:1234/metrics") is True

    def test_no_filters_returns_first_target(self, prom):
        prom.session.get.return_value = _mock_response(self._targets_payload)
        assert prom.has_target() is True

    def test_empty_targets(self, prom):
        prom.session.get.return_value = _mock_response(
            {"data": {"activeTargets": [], "droppedTargets": []}}
        )
        assert prom.has_target(job="prometheus") is False

    def test_missing_data_key(self, prom):
        prom.session.get.return_value = _mock_response({})
        assert prom.has_target(job="prometheus") is False
