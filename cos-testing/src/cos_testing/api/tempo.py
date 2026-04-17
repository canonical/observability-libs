"""Tempo API client for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_exponential


@dataclass
class Tempo:
    """Client for the Tempo HTTP API."""

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
        self.search = self._retry_on_error(self.search)
        self.get_trace = self._retry_on_error(self.get_trace)
        self.get_tags = self._retry_on_error(self.get_tags)
        self.get_tag_values = self._retry_on_error(self.get_tag_values)

    # --- HTTP methods (public, return parsed data) ---

    def search(
        self,
        query: str,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Search for traces using a TraceQL query."""
        params: dict[str, str | int] = {"q": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if limit is not None:
            params["limit"] = limit
        resp = self.session.get(f"{self.url}/api/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_trace(self, trace_id: str) -> dict:
        """Retrieve a trace by its ID."""
        resp = self.session.get(f"{self.url}/api/traces/{trace_id}")
        resp.raise_for_status()
        return resp.json()

    def get_tags(self, scope: str | None = None) -> dict:
        """Fetch all discoverable tag names.

        ``scope`` can be ``resource``, ``span``, or ``intrinsic``.
        """
        params: dict[str, str] = {}
        if scope:
            params["scope"] = scope
        resp = self.session.get(f"{self.url}/api/search/tags", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_tag_values(self, tag: str, query: str | None = None) -> dict:
        """Fetch all values for a given tag.

        An optional TraceQL ``query`` can be provided to filter results.
        """
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        resp = self.session.get(f"{self.url}/api/search/tag/{tag}/values", params=params)
        resp.raise_for_status()
        return resp.json()

    # --- Check methods (public, return bool) ---

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
