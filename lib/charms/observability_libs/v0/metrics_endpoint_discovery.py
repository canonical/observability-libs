# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""# MetricsEndpointDiscovery Library.

This library provides functionality for discovering metrics endpoints exposed
by applications deployed to a Kubernetes cluster.

It comprises:
- A custom event and event source for handling metrics endpoint changes.
- Logic to observe cluster events and emit the events as appropriate.

## Using the Library

### Handling Events

To ensure that your charm can react to changing metrics endpoint events,
use the CharmEvents extension.
```python
from charms.observability_libs.v0.metrics_endpoint_discovery import MetricsEndpointCharmEvents

class MyCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)

        self.metrics_endpoint_observer = MetricsEndpointObserver()

        self.framework.observe(
            self.metrics_endpoint_observer.on.metrics_endpoint_change,
            self._on_metrics_endpoint_change
        )

    def _on_metrics_endpoint_change(self, event):
        self.unit.status = ActiveStatus("metrics endpoints changed")
```
"""

from ops.charm import CharmBase, CharmEvents
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "a141d5620152466781ed83aafb948d03"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


class MetricsEndpointChangeEvent(EventBase):
    """A custom event for metrics endpoint changes."""

    pass


class MetricsEndpointChangeCharmEvents(CharmEvents):
    """A CharmEvents extension for metrics endpoint changes.

    Includes :class:`MetricsEndpointChangeEvent` in those that can be handled.
    """

    metrics_endpoint_change = EventSource(MetricsEndpointChangeEvent)


class MetricsEndpointObserver(Object):
    """Observes changing metrics endpoints in the cluster.

    Observed endpoint changes cause :class"`MetricsEndpointChangeEvent` to be emitted.
    """

    on = MetricsEndpointChangeCharmEvents()

    def __init__(self, charm: CharmBase):
        super().__init__(charm, "metrics-endpoint-observer")
