"""Mimir API client for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_exponential


@dataclass
class Mimir:
    """Client for the Mimir HTTP API (Prometheus-compatible endpoints)."""

    url: str
    headers: dict[str, str] | None = None
    timeout: int = 60
    session: requests.Session = field(init=False, repr=False)
    _retry_on_error: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        if self.headers:
            self.session.headers.update(self.headers)
        self._retry_on_error = retry(
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
            wait=wait_exponential(multiplier=1, max=30),
            stop=stop_after_delay(self.timeout),
            reraise=True,
        )
        self.query = self._retry_on_error(self.query)
        self.query_range = self._retry_on_error(self.query_range)
        self.get_rules = self._retry_on_error(self.get_rules)
        self.get_alerts = self._retry_on_error(self.get_alerts)

    # --- HTTP methods (public, return parsed data) ---

    def query(self, promql: str) -> dict:
        """Execute an instant PromQL query via the Prometheus-compatible API."""
        resp = self.session.get(f"{self.url}/prometheus/api/v1/query", params={"query": promql})
        resp.raise_for_status()
        return resp.json()

    def query_range(self, promql: str, start: str, end: str, step: str = "15s") -> dict:
        """Execute a range PromQL query via the Prometheus-compatible API."""
        resp = self.session.get(
            f"{self.url}/prometheus/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        return resp.json()

    def get_rules(self) -> dict:
        """Fetch all recording and alerting rules."""
        resp = self.session.get(f"{self.url}/prometheus/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    def get_alerts(self) -> dict:
        """Fetch all active alerts."""
        resp = self.session.get(f"{self.url}/prometheus/api/v1/alerts")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def has_metric(self, name: str, labels: dict[str, str] | None = None) -> bool:
        """Check whether a metric with the given name (and optional labels) has data."""
        label_selector = ""
        if labels:
            pairs = ", ".join(f'{k}="{v}"' for k, v in labels.items())
            label_selector = f"{{{pairs}}}"
        result = self.query(f"{name}{label_selector}")
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
