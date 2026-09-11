"""Tests for the Grafana API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from observability_clients.api.grafana import Grafana


@pytest.fixture()
def grafana() -> Grafana:
    """Create a Grafana client with retries disabled."""
    g = Grafana(url="http://grafana:3000")
    g._retry_wait = wait_none()
    g.session = MagicMock()
    return g


@pytest.fixture()
def mock_get(grafana: Grafana) -> MagicMock:
    """Return the mock for ``grafana.session.get``."""
    return grafana.session.get


def _ok_response(json_data: object) -> MagicMock:
    """Build a mock response with the given JSON payload."""
    resp = MagicMock(spec=requests.Response)
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def _http_error_response(status_code: int = 404) -> MagicMock:
    """Build a mock response that raises HTTPError on ``raise_for_status``."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# -------------------------------------------------------------------
# Construction / headers
# -------------------------------------------------------------------


class TestInit:
    def test_no_headers(self) -> None:
        g = Grafana(url="http://grafana:3000")
        assert g.url == "http://grafana:3000"
        assert g.headers is None
        assert isinstance(g.session, requests.Session)

    def test_headers_applied(self) -> None:
        headers = {"Authorization": "Bearer tok123"}
        g = Grafana(url="http://grafana:3000", headers=headers)
        assert g.session.headers["Authorization"] == "Bearer tok123"

    def test_default_timeout(self) -> None:
        g = Grafana(url="http://grafana:3000")
        assert g.timeout == 60

    def test_custom_timeout(self) -> None:
        g = Grafana(url="http://grafana:3000", timeout=120)
        assert g.timeout == 120
        assert g._retry_stop.max_delay == 120


# -------------------------------------------------------------------
# HTTP methods
# -------------------------------------------------------------------


class TestSearchDashboards:
    def test_without_query(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"uid": "a", "title": "Dash A"}])

        result = grafana.search_dashboards()

        mock_get.assert_called_once_with(
            "http://grafana:3000/api/search", params={"type": "dash-db"}
        )
        assert result == [{"uid": "a", "title": "Dash A"}]

    def test_with_query(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"uid": "b", "title": "My Dash"}])

        result = grafana.search_dashboards(query="My Dash")

        mock_get.assert_called_once_with(
            "http://grafana:3000/api/search",
            params={"type": "dash-db", "query": "My Dash"},
        )
        assert result == [{"uid": "b", "title": "My Dash"}]

    def test_raises_on_http_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(500)

        with pytest.raises(requests.HTTPError):
            grafana.search_dashboards()


class TestGetDashboard:
    def test_success(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"dashboard": {"id": 1}})

        result = grafana.get_dashboard("abc")

        mock_get.assert_called_once_with("http://grafana:3000/api/dashboards/uid/abc")
        assert result == {"dashboard": {"id": 1}}

    def test_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        with pytest.raises(requests.HTTPError):
            grafana.get_dashboard("missing")


class TestGetDatasources:
    def test_success(self, grafana: Grafana, mock_get: MagicMock) -> None:
        payload = [{"name": "Prometheus", "type": "prometheus"}]
        mock_get.return_value = _ok_response(payload)

        result = grafana.get_datasources()

        mock_get.assert_called_once_with("http://grafana:3000/api/datasources")
        assert result == payload

    def test_raises_on_http_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(403)

        with pytest.raises(requests.HTTPError):
            grafana.get_datasources()


class TestGetDatasourceByName:
    def test_success(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"name": "Loki", "type": "loki"})

        result = grafana.get_datasource_by_name("Loki")

        mock_get.assert_called_once_with("http://grafana:3000/api/datasources/name/Loki")
        assert result == {"name": "Loki", "type": "loki"}

    def test_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        with pytest.raises(requests.HTTPError):
            grafana.get_datasource_by_name("nope")


class TestGetDatasourceHealth:
    def test_success(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"status": "OK", "message": "all good"})

        result = grafana.get_datasource_health("abc123")

        mock_get.assert_called_once_with("http://grafana:3000/api/datasources/uid/abc123/health")
        assert result == {"status": "OK", "message": "all good"}

    def test_raises_on_http_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        with pytest.raises(requests.HTTPError):
            grafana.get_datasource_health("missing")


class TestGetAlertRules:
    def test_success(self, grafana: Grafana, mock_get: MagicMock) -> None:
        payload = {"ns": [{"name": "grp", "rules": []}]}
        mock_get.return_value = _ok_response(payload)

        result = grafana.get_alert_rules()

        mock_get.assert_called_once_with("http://grafana:3000/api/ruler/grafana/api/v1/rules")
        assert result == payload

    def test_raises_on_http_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(500)

        with pytest.raises(requests.HTTPError):
            grafana.get_alert_rules()


# -------------------------------------------------------------------
# Check methods
# -------------------------------------------------------------------


class TestHasDashboard:
    def test_by_uid_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"dashboard": {"uid": "abc"}})

        assert grafana.has_dashboard(uid="abc") is True

    def test_by_uid_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        assert grafana.has_dashboard(uid="missing") is False

    def test_by_title_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"title": "CPU Usage"}, {"title": "Memory"}])

        assert grafana.has_dashboard(title="CPU Usage") is True

    def test_by_title_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"title": "Memory"}])

        assert grafana.has_dashboard(title="CPU Usage") is False

    def test_no_args_dashboards_exist(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"title": "Something"}])

        assert grafana.has_dashboard() is True

    def test_no_args_no_dashboards(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([])

        assert grafana.has_dashboard() is False


class TestHasDashboardWithTag:
    def test_tag_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(
            [
                {"title": "A", "tags": ["monitoring", "infra"]},
                {"title": "B", "tags": ["app"]},
            ]
        )
        assert grafana.has_dashboard_with_tag("monitoring") is True

    def test_tag_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(
            [
                {"title": "A", "tags": ["monitoring"]},
            ]
        )
        assert grafana.has_dashboard_with_tag("database") is False

    def test_no_dashboards(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([])
        assert grafana.has_dashboard_with_tag("any") is False

    def test_dashboard_without_tags_key(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"title": "A"}])
        assert grafana.has_dashboard_with_tag("infra") is False


class TestHasDatasource:
    def test_by_name_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"name": "Prometheus", "type": "prometheus"})

        assert grafana.has_datasource(name="Prometheus") is True

    def test_by_name_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        assert grafana.has_datasource(name="nope") is False

    def test_by_type_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"name": "Prometheus", "type": "prometheus"}])

        assert grafana.has_datasource(type="prometheus") is True

    def test_by_type_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"name": "Prometheus", "type": "prometheus"}])

        assert grafana.has_datasource(type="loki") is False

    def test_by_name_and_type_match(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"name": "Prometheus", "type": "prometheus"}])

        assert grafana.has_datasource(name="Prometheus", type="prometheus") is True

    def test_by_name_and_type_no_match(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"name": "Prometheus", "type": "prometheus"}])

        assert grafana.has_datasource(name="Prometheus", type="loki") is False

    def test_by_name_and_type_name_mismatch(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response([{"name": "Other", "type": "prometheus"}])

        assert grafana.has_datasource(name="Prometheus", type="prometheus") is False

    def test_no_args_raises(self, grafana: Grafana, mock_get: MagicMock) -> None:
        with pytest.raises(ValueError, match="At least one of"):
            grafana.has_datasource()


class TestIsDatasourceHealthy:
    def test_by_uid_healthy(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"status": "OK", "message": "all good"})

        assert grafana.is_datasource_healthy(uid="abc123") is True
        mock_get.assert_called_once_with("http://grafana:3000/api/datasources/uid/abc123/health")

    def test_by_uid_unhealthy(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response({"status": "ERROR", "message": "unreachable"})

        assert grafana.is_datasource_healthy(uid="abc123") is False

    def test_by_uid_http_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        assert grafana.is_datasource_healthy(uid="missing") is False

    def test_by_name_resolves_uid(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.side_effect = [
            _ok_response({"name": "Loki", "uid": "loki-uid"}),
            _ok_response({"status": "OK", "message": "all good"}),
        ]

        assert grafana.is_datasource_healthy(name="Loki") is True
        assert mock_get.call_args_list[0].args[0] == (
            "http://grafana:3000/api/datasources/name/Loki"
        )
        assert mock_get.call_args_list[1].args[0] == (
            "http://grafana:3000/api/datasources/uid/loki-uid/health"
        )

    def test_by_name_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _http_error_response(404)

        assert grafana.is_datasource_healthy(name="nope") is False

    def test_no_args_raises(self, grafana: Grafana, mock_get: MagicMock) -> None:
        with pytest.raises(ValueError, match="At least one of"):
            grafana.is_datasource_healthy()


class TestHasAlertRule:
    _ALERT_DATA = {
        "namespace-1": [
            {
                "name": "group-a",
                "rules": [
                    {"alert": "HighCPU"},
                    {"grafana_alert": {"title": "DiskFull"}},
                ],
            },
            {
                "name": "group-b",
                "rules": [
                    {"alert": "MemoryHigh"},
                ],
            },
        ],
    }

    def test_match_by_alert_key(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(self._ALERT_DATA)

        assert grafana.has_alert_rule("HighCPU") is True

    def test_match_by_grafana_alert_title(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(self._ALERT_DATA)

        assert grafana.has_alert_rule("DiskFull") is True

    def test_with_group_filter_match(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(self._ALERT_DATA)

        assert grafana.has_alert_rule("HighCPU", group="group-a") is True

    def test_with_group_filter_no_match(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(self._ALERT_DATA)

        assert grafana.has_alert_rule("HighCPU", group="group-b") is False

    def test_rule_not_found(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(self._ALERT_DATA)

        assert grafana.has_alert_rule("NoSuchRule") is False

    def test_non_list_namespace_skipped(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok_response(
            {"status": "success", "ns": [{"name": "g", "rules": [{"alert": "X"}]}]}
        )

        assert grafana.has_alert_rule("X") is True
        # "status" key has a string value, not a list — should be silently skipped
        assert grafana.has_alert_rule("Y") is False


class TestIsReady:
    def test_ready(self, grafana: Grafana, mock_get: MagicMock) -> None:
        resp = _ok_response({"database": "ok", "version": "10.0.0"})
        resp.status_code = 200
        mock_get.return_value = resp
        assert grafana.is_ready() is True
        mock_get.assert_called_once_with("http://grafana:3000/api/health")

    def test_database_not_ok(self, grafana: Grafana, mock_get: MagicMock) -> None:
        resp = _ok_response({"database": "failing"})
        resp.status_code = 200
        mock_get.return_value = resp
        assert grafana.is_ready() is False

    def test_non_200_status(self, grafana: Grafana, mock_get: MagicMock) -> None:
        resp = _ok_response({"database": "ok"})
        resp.status_code = 503
        mock_get.return_value = resp
        assert grafana.is_ready() is False

    def test_connection_error(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.ConnectionError("connection refused")
        assert grafana.is_ready() is False

    def test_timeout(self, grafana: Grafana, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        assert grafana.is_ready() is False
