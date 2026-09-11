"""Tests for the Alertmanager API client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from tenacity import wait_none

from observability_clients.api.alertmanager import Alertmanager

BASE_URL = "http://alertmanager:9093"


@pytest.fixture()
def alertmanager() -> Alertmanager:
    """Return an Alertmanager client with retries disabled."""
    client = Alertmanager(url=BASE_URL)
    client._retry_wait = wait_none()
    client.session = MagicMock(spec=requests.Session)
    return client


@pytest.fixture()
def mock_get(alertmanager: Alertmanager) -> MagicMock:
    """Return the mock for ``alertmanager.session.get``."""
    return alertmanager.session.get


def _mock_response(json_data: object, status_code: int = 200) -> MagicMock:
    """Build a mock ``requests.Response``."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ── Initialization ───────────────────────────────────────────────────────────


class TestInit:
    def test_creates_session(self):
        client = Alertmanager(url=BASE_URL)
        assert client.session is not None

    def test_headers_applied(self):
        client = Alertmanager(url=BASE_URL, headers={"Authorization": "Bearer tok"})
        assert client.session.headers["Authorization"] == "Bearer tok"

    def test_default_timeout(self):
        client = Alertmanager(url=BASE_URL)
        assert client.timeout == 60

    def test_verify_disabled(self):
        client = Alertmanager(url=BASE_URL)
        assert client.session.verify is False


# ── get_alerts ───────────────────────────────────────────────────────────────


class TestGetAlerts:
    def test_default_params(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response([])

        result = alertmanager.get_alerts()

        mock_get.assert_called_once_with(
            f"{BASE_URL}/api/v2/alerts",
            params={"active": "true", "silenced": "false", "inhibited": "false"},
        )
        assert result == []

    def test_custom_params(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response([])

        alertmanager.get_alerts(active=False, silenced=True, inhibited=True)

        mock_get.assert_called_once_with(
            f"{BASE_URL}/api/v2/alerts",
            params={"active": "false", "silenced": "true", "inhibited": "true"},
        )

    def test_raises_on_http_error(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        resp = _mock_response({}, status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = resp

        with pytest.raises(requests.HTTPError, match="500 Server Error"):
            alertmanager.get_alerts()


# ── get_silences ─────────────────────────────────────────────────────────────


class TestGetSilences:
    def test_returns_json(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        payload = [{"id": "abc", "comment": "maintenance"}]
        mock_get.return_value = _mock_response(payload)

        result = alertmanager.get_silences()

        mock_get.assert_called_once_with(f"{BASE_URL}/api/v2/silences")
        assert result == payload


# ── is_ready ─────────────────────────────────────────────────────────────────


class TestIsReady:
    def test_ready(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response({}, status_code=200)
        assert alertmanager.is_ready() is True
        mock_get.assert_called_once_with(f"{BASE_URL}/-/ready")

    def test_not_ready(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response({}, status_code=503)
        assert alertmanager.is_ready() is False

    def test_connection_error(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.ConnectionError("connection refused")
        assert alertmanager.is_ready() is False

    def test_timeout(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        assert alertmanager.is_ready() is False


# ── has_active_alert ─────────────────────────────────────────────────────────


class TestHasActiveAlert:
    def test_found(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                    "status": {"state": "active"},
                }
            ]
        )
        assert alertmanager.has_active_alert("HighCPU") is True

    def test_not_found(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response([])
        assert alertmanager.has_active_alert("HighCPU") is False

    def test_wrong_name(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [{"labels": {"alertname": "Other"}, "status": {"state": "active"}}]
        )
        assert alertmanager.has_active_alert("HighCPU") is False

    def test_matches_labels(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "labels": {"alertname": "HighCPU", "env": "prod"},
                    "status": {"state": "active"},
                }
            ]
        )
        assert alertmanager.has_active_alert("HighCPU", labels={"env": "prod"}) is True
        assert alertmanager.has_active_alert("HighCPU", labels={"env": "staging"}) is False

    def test_suppressed_alert_not_active(
        self, alertmanager: Alertmanager, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(
            [{"labels": {"alertname": "HighCPU"}, "status": {"state": "suppressed"}}]
        )
        assert alertmanager.has_active_alert("HighCPU") is False

    def test_uses_active_only_params(
        self, alertmanager: Alertmanager, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response([])
        alertmanager.has_active_alert("HighCPU")
        mock_get.assert_called_once_with(
            f"{BASE_URL}/api/v2/alerts",
            params={"active": "true", "silenced": "false", "inhibited": "false"},
        )


# ── has_silence ──────────────────────────────────────────────────────────────


class TestHasSilence:
    def test_found_by_comment(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [{"comment": "maintenance window", "matchers": [], "status": {"state": "active"}}]
        )
        assert alertmanager.has_silence(comment="maintenance window") is True

    def test_not_found(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response([])
        assert alertmanager.has_silence(comment="anything") is False

    def test_filter_by_state(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [{"comment": "old", "matchers": [], "status": {"state": "expired"}}]
        )
        assert alertmanager.has_silence(comment="old", state="active") is False
        assert alertmanager.has_silence(comment="old", state="expired") is True

    def test_filter_by_matchers(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "comment": "maintenance",
                    "matchers": [{"name": "alertname", "value": "HighCPU"}],
                    "status": {"state": "active"},
                }
            ]
        )
        assert alertmanager.has_silence(matchers={"alertname": "HighCPU"}) is True
        assert alertmanager.has_silence(matchers={"alertname": "Other"}) is False

    def test_no_criteria_matches_any(
        self, alertmanager: Alertmanager, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(
            [{"comment": "x", "matchers": [], "status": {"state": "active"}}]
        )
        assert alertmanager.has_silence() is True

    def test_skips_non_matching_comment(
        self, alertmanager: Alertmanager, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(
            [
                {"comment": "other", "matchers": [], "status": {"state": "active"}},
                {"comment": "target", "matchers": [], "status": {"state": "active"}},
            ]
        )
        assert alertmanager.has_silence(comment="target") is True


# ── is_silenced ──────────────────────────────────────────────────────────────


class TestIsSilenced:
    def test_silenced_alert_found(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "labels": {"alertname": "HighCPU"},
                    "status": {"state": "suppressed", "silencedBy": ["abc123"]},
                }
            ]
        )
        assert alertmanager.has_silenced_alert("HighCPU") is True

    def test_not_silenced(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "labels": {"alertname": "HighCPU"},
                    "status": {"state": "active", "silencedBy": []},
                }
            ]
        )
        assert alertmanager.has_silenced_alert("HighCPU") is False

    def test_not_found(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response([])
        assert alertmanager.has_silenced_alert("HighCPU") is False

    def test_matches_labels(self, alertmanager: Alertmanager, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            [
                {
                    "labels": {"alertname": "HighCPU", "env": "prod"},
                    "status": {"state": "suppressed", "silencedBy": ["abc123"]},
                }
            ]
        )
        assert alertmanager.has_silenced_alert("HighCPU", labels={"env": "prod"}) is True
        assert alertmanager.has_silenced_alert("HighCPU", labels={"env": "staging"}) is False

    def test_skips_non_matching_name(
        self, alertmanager: Alertmanager, mock_get: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(
            [
                {"labels": {"alertname": "Other"}, "status": {"silencedBy": ["abc"]}},
                {
                    "labels": {"alertname": "HighCPU"},
                    "status": {"silencedBy": ["abc123"]},
                },
            ]
        )
        assert alertmanager.has_silenced_alert("HighCPU") is True
