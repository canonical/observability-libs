"""Loki API client for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_exponential


@dataclass
class Loki:
    """Client for the Loki HTTP API."""

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
        self.get_labels = self._retry_on_error(self.get_labels)
        self.get_label_values = self._retry_on_error(self.get_label_values)
        self.get_rules = self._retry_on_error(self.get_rules)

    # --- HTTP methods (public, return parsed data) ---

    def query(self, logql: str) -> dict:
        """Execute an instant LogQL query."""
        resp = self.session.get(f"{self.url}/loki/api/v1/query", params={"query": logql})
        resp.raise_for_status()
        return resp.json()

    def query_range(
        self,
        logql: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Execute a range LogQL query."""
        params: dict[str, str | int] = {"query": logql, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        resp = self.session.get(f"{self.url}/loki/api/v1/query_range", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_labels(self) -> dict:
        """Fetch all label names."""
        resp = self.session.get(f"{self.url}/loki/api/v1/labels")
        resp.raise_for_status()
        return resp.json()

    def get_label_values(self, label: str) -> dict:
        """Fetch all values for a given label."""
        resp = self.session.get(f"{self.url}/loki/api/v1/label/{label}/values")
        resp.raise_for_status()
        return resp.json()

    def get_rules(self) -> dict:
        """Fetch all alerting and recording rules."""
        resp = self.session.get(f"{self.url}/loki/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def has_log_line(self, query: str, pattern: str | None = None) -> bool:
        """Check whether any log lines match the LogQL query.

        If ``pattern`` is provided, at least one returned log line must contain it.
        """
        import re

        result = self.query(query)
        entries = result.get("data", {}).get("result", [])
        if not entries:
            return False
        if pattern is None:
            return True
        compiled = re.compile(pattern)
        for stream in entries:
            for _ts, line in stream.get("values", []):
                if compiled.search(line):
                    return True
        return False

    def has_label(self, name: str) -> bool:
        """Check whether a label with the given name exists."""
        data = self.get_labels()
        return name in data.get("data", [])

    def has_label_value(self, name: str, value: str) -> bool:
        """Check whether a label has a specific value."""
        data = self.get_label_values(name)
        return value in data.get("data", [])

    def has_alert_rule(self, name: str, group: str | None = None) -> bool:
        """Check whether an alerting rule with the given name exists."""
        data = self.get_rules()
        # Loki rules response can be either Prometheus-style or grouped by namespace.
        groups = data.get("data", {}).get("groups", [])
        if not groups:
            for _ns, ns_groups in data.get("data", {}).items():
                if isinstance(ns_groups, list):
                    groups.extend(ns_groups)
        for rule_group in groups:
            if group and rule_group.get("name") != group:
                continue
            for rule in rule_group.get("rules", []):
                if rule.get("name") == name or rule.get("alert") == name:
                    return True
        return False

    def has_alert_rules(self, labels: dict[str, str]) -> bool:
        """Check whether any alerting rule exists whose labels contain all the given key-value pairs."""
        data = self.get_rules()
        groups: list = data.get("data", {}).get("groups", [])
        if not groups:
            for _ns, ns_groups in data.get("data", {}).items():
                if isinstance(ns_groups, list):
                    groups.extend(ns_groups)
        for rule_group in groups:
            for rule in rule_group.get("rules", []):
                rule_labels = rule.get("labels", {})
                if all(rule_labels.get(k) == v for k, v in labels.items()):
                    return True
        return False
