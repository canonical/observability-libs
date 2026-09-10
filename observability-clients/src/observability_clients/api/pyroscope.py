"""Pyroscope API client for testing."""

from __future__ import annotations

from dataclasses import dataclass

from observability_clients.api._base import BaseClient


@dataclass
class Pyroscope(BaseClient):
    """Client for the Pyroscope HTTP API."""

    # --- HTTP methods (public, return parsed data) ---

    def render(
        self,
        query: str,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        """Query profile data as a flamebearer.

        ``query`` uses the Pyroscope selector syntax, e.g.
        ``process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="myapp"}``.
        ``start`` / ``end`` accept epoch seconds or relative strings like ``now-1h``.
        """
        params: dict[str, str] = {"query": query, "format": "json"}
        if start:
            params["from"] = start
        if end:
            params["until"] = end
        resp = self._get("/pyroscope/render", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_profile_types(self) -> dict:
        """Fetch all available profile types."""
        resp = self._post(
            "/querier.v1.QuerierService/ProfileTypes",
            json={},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def get_labels(self) -> dict:
        """Fetch all label names."""
        resp = self._post(
            "/querier.v1.QuerierService/LabelNames",
            json={},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def get_label_values(self, label: str) -> list:
        """Fetch all values for a given label.

        Returns a plain JSON array of strings.
        """
        resp = self._get(
            "/pyroscope/label-values",
            params={"label": label},
        )
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def has_profile(self, query: str) -> bool:
        """Check whether profile data exists for the given query."""
        result = self.render(query)
        return result.get("flamebearer", {}).get("numTicks", 0) > 0

    def has_profile_type(self, profile_type_id: str) -> bool:
        """Check whether a profile type with the given ID is available."""
        data = self.get_profile_types()
        return profile_type_id in [pt.get("id") for pt in data.get("profileTypes", [])]

    def has_label(self, name: str) -> bool:
        """Check whether a label with the given name exists."""
        data = self.get_labels()
        return name in data.get("names", [])

    def has_label_value(self, label: str, value: str) -> bool:
        """Check whether a label has a specific value."""
        values = self.get_label_values(label)
        if not isinstance(values, list):
            return False
        return value in values
