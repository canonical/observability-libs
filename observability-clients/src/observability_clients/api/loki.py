"""Loki API client for testing."""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from observability_clients.api._base import BaseClient


@dataclass
class Loki(BaseClient):
    """Client for the Loki HTTP API."""

    # --- HTTP methods (public, return parsed data) ---

    def query(self, logql: str) -> dict:
        """Execute an instant LogQL query."""
        resp = self._get("/loki/api/v1/query", params={"query": logql})
        resp.raise_for_status()
        return resp.json()

    def query_range(
        self,
        logql: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict:
        """Execute a range LogQL query."""
        params: dict[str, str | int] = {"query": logql, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        resp = self._get("/loki/api/v1/query_range", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_labels(self) -> dict:
        """Fetch all label names."""
        resp = self._get("/loki/api/v1/labels")
        resp.raise_for_status()
        return resp.json()

    def get_label_values(self, label: str) -> dict:
        """Fetch all values for a given label."""
        resp = self._get(f"/loki/api/v1/label/{label}/values")
        resp.raise_for_status()
        return resp.json()

    def get_rules(self) -> dict:
        """Fetch all alerting and recording rules."""
        resp = self._get("/loki/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def is_ready(self, path: str = "/ready") -> bool:
        """Check whether Loki is ready."""
        try:
            resp = self.session.get(f"{self.url}{path}")
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def has_log_line(self, query: str, pattern: str | None = None) -> bool:
        """Check whether any log lines match the LogQL query.

        If ``pattern`` is provided, at least one returned log line must contain it.
        """
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
