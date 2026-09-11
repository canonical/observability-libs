"""Mimir API client for testing."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from observability_clients.api._base import BaseClient


@dataclass
class Mimir(BaseClient):
    """Client for the Mimir HTTP API (Prometheus-compatible endpoints)."""

    # --- HTTP methods (public, return parsed data) ---

    def query(self, promql: str) -> dict:
        """Execute an instant PromQL query via the Prometheus-compatible API."""
        resp = self._get("/prometheus/api/v1/query", params={"query": promql})
        resp.raise_for_status()
        return resp.json()

    def query_range(self, promql: str, start: str, end: str, step: str = "15s") -> dict:
        """Execute a range PromQL query via the Prometheus-compatible API."""
        resp = self._get(
            "/prometheus/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        return resp.json()

    def get_rules(self) -> dict:
        """Fetch all recording and alerting rules."""
        resp = self._get("/prometheus/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    def get_alerts(self) -> dict:
        """Fetch all active alerts."""
        resp = self._get("/prometheus/api/v1/alerts")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def is_ready(self, path: str = "/ready") -> bool:
        """Check whether Mimir is ready."""
        try:
            resp = self.session.get(f"{self.url}{path}")
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def has_metric(self, name: str | None = None, labels: dict[str, str] | None = None) -> bool:
        """Check whether a metric with the given name and/or labels has data.

        At least one of ``name`` or ``labels`` must be provided.
        """
        if not name and not labels:
            raise ValueError("At least one of 'name' or 'labels' must be provided.")
        label_selector = ""
        if labels:
            pairs = ", ".join(f'{k}="{v}"' for k, v in labels.items())
            label_selector = f"{{{pairs}}}"
        result = self.query(f"{name or ''}{label_selector}")
        return len(result.get("data", {}).get("result", [])) > 0

    def has_alert_rule(self, name: str, group: str | None = None) -> bool:
        """Check whether an alerting rule with the given name exists."""
        data = self.get_rules()
        for rule_group in data.get("data", {}).get("groups", []):
            if group and rule_group.get("name") != group:
                continue
            for rule in rule_group.get("rules", []):
                if rule.get("name") == name and rule.get("type") == "alerting":
                    return True
        return False

    def has_alert_rules(self, labels: dict[str, str]) -> bool:
        """Check whether any alerting rule exists whose labels contain all the given key-value pairs."""
        data = self.get_rules()
        for rule_group in data.get("data", {}).get("groups", []):
            for rule in rule_group.get("rules", []):
                if rule.get("type") != "alerting":
                    continue
                rule_labels = rule.get("labels", {})
                if all(rule_labels.get(k) == v for k, v in labels.items()):
                    return True
        return False

    def has_active_alert(self, name: str, labels: dict[str, str] | None = None) -> bool:
        """Check whether an alert with the given name is currently firing."""
        data = self.get_alerts()
        for alert in data.get("data", {}).get("alerts", []):
            alert_labels = alert.get("labels", {})
            if alert_labels.get("alertname") != name:
                continue
            if labels and not all(alert_labels.get(k) == v for k, v in labels.items()):
                continue
            return True
        return False
