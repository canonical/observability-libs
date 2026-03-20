"""Grafana API client for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_exponential


@dataclass
class Grafana:
    """Client for the Grafana HTTP API."""

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
        self.search_dashboards = self._retry_on_error(self.search_dashboards)
        self.get_dashboard = self._retry_on_error(self.get_dashboard)
        self.get_datasources = self._retry_on_error(self.get_datasources)
        self.get_datasource_by_name = self._retry_on_error(self.get_datasource_by_name)
        self.get_alert_rules = self._retry_on_error(self.get_alert_rules)

    # --- HTTP methods (public, return parsed data) ---

    def search_dashboards(self, query: str | None = None) -> list[dict]:
        """Search dashboards by title or return all."""
        params: dict[str, str] = {"type": "dash-db"}
        if query:
            params["query"] = query
        resp = self.session.get(f"{self.url}/api/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_dashboard(self, uid: str) -> dict:
        """Fetch a specific dashboard by UID."""
        resp = self.session.get(f"{self.url}/api/dashboards/uid/{uid}")
        resp.raise_for_status()
        return resp.json()

    def get_datasources(self) -> list[dict]:
        """Fetch all configured datasources."""
        resp = self.session.get(f"{self.url}/api/datasources")
        resp.raise_for_status()
        return resp.json()

    def get_datasource_by_name(self, name: str) -> dict:
        """Fetch a specific datasource by name."""
        resp = self.session.get(f"{self.url}/api/datasources/name/{name}")
        resp.raise_for_status()
        return resp.json()

    def get_alert_rules(self) -> dict:
        """Fetch all Grafana-managed alert rules."""
        resp = self.session.get(f"{self.url}/api/ruler/grafana/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def has_dashboard(self, title: str | None = None, uid: str | None = None) -> bool:
        """Check whether a dashboard exists by title and/or UID."""
        if uid:
            try:
                self.get_dashboard(uid)
                return True
            except requests.HTTPError:
                return False
        dashboards = self.search_dashboards(query=title)
        if title:
            return any(d.get("title") == title for d in dashboards)
        return len(dashboards) > 0

    def has_dashboard_with_tag(self, tag: str) -> bool:
        """Check whether any dashboard has the given tag."""
        dashboards = self.search_dashboards()
        return any(tag in d.get("tags", []) for d in dashboards)

    def has_datasource(self, name: str | None = None, type: str | None = None) -> bool:
        """Check whether a datasource exists matching the given criteria."""
        if name and not type:
            try:
                self.get_datasource_by_name(name)
                return True
            except requests.HTTPError:
                return False
        datasources = self.get_datasources()
        for ds in datasources:
            if name and ds.get("name") != name:
                continue
            if type and ds.get("type") != type:
                continue
            return True
        return False

    def has_alert_rule(self, name: str, group: str | None = None) -> bool:
        """Check whether a Grafana-managed alert rule with the given name exists."""
        data = self.get_alert_rules()
        # Response is keyed by namespace (folder), each containing a list of rule groups.
        for _namespace, rule_groups in data.items():
            if not isinstance(rule_groups, list):
                continue
            for rule_group in rule_groups:
                if group and rule_group.get("name") != group:
                    continue
                for rule in rule_group.get("rules", []):
                    if (
                        rule.get("alert") == name
                        or rule.get("grafana_alert", {}).get("title") == name
                    ):
                        return True
        return False
