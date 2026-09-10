"""Shared HTTP client base for the Observability stack API clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
import urllib3
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)
from tenacity.stop import stop_base
from tenacity.wait import wait_base

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class BaseClient:
    """Shared HTTP plumbing for Observability component API clients."""

    url: str
    headers: dict[str, str] | None = None
    timeout: int = 60
    session: requests.Session = field(init=False, repr=False)
    _retry_wait: wait_base = field(init=False, repr=False)
    _retry_stop: stop_base = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.verify = False
        if self.headers:
            self.session.headers.update(self.headers)
        self._retry_wait = wait_exponential(multiplier=1, max=30)
        self._retry_stop = stop_after_delay(self.timeout)

    def _retrying(self):
        """Build a ``Retrying`` wrapper using this client's retry policy."""
        return retry(
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
            wait=self._retry_wait,
            stop=self._retry_stop,
            reraise=True,
        )

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        """Send a GET request to ``path``, retrying on connection errors/timeouts."""
        return self._retrying()(self.session.get)(f"{self.url}{path}", **kwargs)

    def _post(self, path: str, **kwargs: Any) -> requests.Response:
        """Send a POST request to ``path``, retrying on connection errors/timeouts."""
        return self._retrying()(self.session.post)(f"{self.url}{path}", **kwargs)

    def is_ready(self, path: str = "/ready") -> bool:
        """Check whether the component is ready."""
        try:
            resp = self.session.get(f"{self.url}{path}")
        except (requests.ConnectionError, requests.Timeout):
            return False
        return resp.status_code == 200
