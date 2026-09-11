"""Tempo API client for testing."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from observability_clients.api._base import BaseClient


@dataclass
class Tempo(BaseClient):
    """Client for the Tempo HTTP API."""

    # --- HTTP methods (public, return parsed data) ---

    def search(
        self,
        query: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Search for traces using a TraceQL query."""
        params: dict[str, str | int] = {"q": query, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        resp = self._get("/api/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_trace(self, trace_id: str) -> dict:
        """Retrieve a trace by its ID."""
        resp = self._get(f"/api/traces/{trace_id}")
        resp.raise_for_status()
        return resp.json()

    def get_tags(self, scope: str | None = None) -> dict:
        """Fetch all discoverable tag names.

        ``scope`` can be ``resource``, ``span``, or ``intrinsic``.
        """
        params: dict[str, str] = {}
        if scope:
            params["scope"] = scope
        resp = self._get("/api/search/tags", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_tag_values(self, tag: str, query: str | None = None) -> dict:
        """Fetch all values for a given tag.

        An optional TraceQL ``query`` can be provided to filter results.
        """
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        resp = self._get(f"/api/search/tag/{tag}/values", params=params)
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

    def is_ready(self, path: str = "/ready") -> bool:
        """Check whether Tempo is ready."""
        try:
            resp = self.session.get(f"{self.url}{path}")
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200

    def has_trace(self, trace_id: str) -> bool:
        """Check whether a trace with the given ID exists."""
        try:
            self.get_trace(trace_id)
            return True
        except requests.HTTPError:
            return False

    def has_traces(self, query: str) -> bool:
        """Check whether any traces match the given TraceQL query."""
        result = self.search(query)
        return len(result.get("traces", [])) > 0

    def has_tag(self, name: str, scope: str | None = None) -> bool:
        """Check whether a tag with the given name exists."""
        data = self.get_tags(scope=scope)
        return name in [t.get("tagName") for t in data.get("tagNames", [])]

    def has_tag_value(self, tag: str, value: str) -> bool:
        """Check whether a tag has a specific value."""
        data = self.get_tag_values(tag)
        return value in [v.get("value") for v in data.get("tagValues", [])]
