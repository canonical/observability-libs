"""Grafana API client for testing."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from observability_clients.api._base import BaseClient


@dataclass
class Grafana(BaseClient):
    """Client for the Grafana HTTP API."""

    # --- HTTP methods (public, return parsed data) ---

    def search_dashboards(self, query: str | None = None) -> list[dict]:
        """Search dashboards by title or return all."""
        params: dict[str, str] = {"type": "dash-db"}
        if query:
            params["query"] = query
        resp = self._get("/api/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_dashboard(self, uid: str) -> dict:
        """Fetch a specific dashboard by UID."""
        resp = self._get(f"/api/dashboards/uid/{uid}")
        resp.raise_for_status()
        return resp.json()

    def get_datasources(self) -> list[dict]:
        """Fetch all configured datasources."""
        resp = self._get("/api/datasources")
        resp.raise_for_status()
        return resp.json()

    def get_datasource_by_name(self, name: str) -> dict:
        """Fetch a specific datasource by name."""
        resp = self._get(f"/api/datasources/name/{name}")
        resp.raise_for_status()
        return resp.json()

    def get_datasource_health(self, uid: str) -> dict:
        """Check the health of a datasource by UID, regardless of its type.

        Relies on the datasource plugin's ``CheckHealth`` implementation, so the
        response is uniform across datasource types (Prometheus, Loki, Tempo, etc.).
        """
        resp = self._get(f"/api/datasources/uid/{uid}/health")
        resp.raise_for_status()
        return resp.json()

    def get_alert_rules(self) -> dict:
        """Fetch all Grafana-managed alert rules."""
        resp = self._get("/api/ruler/grafana/api/v1/rules")
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def is_ready(self, path: str = "/api/health") -> bool:
        """Check whether Grafana is ready."""
        try:
            resp = self.session.get(f"{self.url}{path}")
        except (requests.ConnectionError, requests.Timeout):
            return False
        if resp.status_code != 200:
            return False
        return resp.json().get("database") == "ok"

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
        """Check whether a datasource exists matching the given criteria.

        At least one of ``name`` or ``type`` must be provided.
        """
        if not name and not type:
            raise ValueError("At least one of 'name' or 'type' must be provided.")
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

    def is_datasource_healthy(self, name: str | None = None, uid: str | None = None) -> bool:
        """Check whether a datasource is healthy, regardless of its type.

        At least one of ``name`` or ``uid`` must be provided. If only ``name``
        is given, the datasource's UID is looked up first.
        """
        if not name and not uid:
            raise ValueError("At least one of 'name' or 'uid' must be provided.")
        if not uid:
            assert name is not None
            try:
                uid = self.get_datasource_by_name(name).get("uid")
            except requests.HTTPError:
                return False
        if not uid:
            return False
        try:
            health = self.get_datasource_health(uid)
        except requests.HTTPError:
            return False
        return health.get("status") == "OK"

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
