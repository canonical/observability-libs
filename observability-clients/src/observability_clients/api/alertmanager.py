"""Alertmanager API client for testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from observability_clients.api._base import BaseClient


@dataclass
class Alertmanager(BaseClient):
    """Client for the Alertmanager HTTP API (v2)."""

    # --- HTTP methods (public, return parsed data) ---

    def get_alerts(
        self,
        active: bool = True,
        silenced: bool = False,
        inhibited: bool = False,
    ) -> list[dict]:
        """Fetch all alerts known to Alertmanager, filtered by state."""
        params = {
            "active": str(active).lower(),
            "silenced": str(silenced).lower(),
            "inhibited": str(inhibited).lower(),
        }
        resp = self._get("/api/v2/alerts", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_silences(self) -> list[dict]:
        """Fetch all silences known to Alertmanager."""
        resp = self._get("/api/v2/silences")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def is_ready(self, path: str = "/-/ready") -> bool:
        """Check whether Alertmanager is ready."""
        return super().is_ready(path=path)

    def has_silence(
        self,
        matchers: dict[str, str] | None = None,
        comment: str | None = None,
        state: Literal["active", "pending", "expired"] | None = None,
    ) -> bool:
        """Check whether a silence exists matching the given criteria.

        ``matchers`` checks that the silence has a matcher for each given
        label name/value pair. ``state`` can be ``active``, ``pending``, or
        ``expired``.
        """
        silences = self.get_silences()
        for silence in silences:
            if comment and silence.get("comment") != comment:
                continue
            if state and silence.get("status", {}).get("state") != state:
                continue
            if matchers:
                silence_matchers = {
                    m.get("name"): m.get("value") for m in silence.get("matchers", [])
                }
                if not all(silence_matchers.get(k) == v for k, v in matchers.items()):
                    continue
            return True
        return False

    def has_active_alert(self, name: str, labels: dict[str, str] | None = None) -> bool:
        """Check whether an alert with the given name is currently active (not suppressed)."""
        alerts = self.get_alerts(active=True, silenced=False, inhibited=False)
        for alert in alerts:
            alert_labels = alert.get("labels", {})
            if alert_labels.get("alertname") != name:
                continue
            if labels and not all(alert_labels.get(k) == v for k, v in labels.items()):
                continue
            if alert.get("status", {}).get("state") != "active":
                continue
            return True
        return False

    def has_silenced_alert(self, name: str, labels: dict[str, str] | None = None) -> bool:
        """Check whether an alert with the given name is currently silenced."""
        alerts = self.get_alerts(active=True, silenced=True, inhibited=True)
        for alert in alerts:
            alert_labels = alert.get("labels", {})
            if alert_labels.get("alertname") != name:
                continue
            if labels and not all(alert_labels.get(k) == v for k, v in labels.items()):
                continue
            if not alert.get("status", {}).get("silencedBy"):
                continue
            return True
        return False
