# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from charms.observability_libs.v0.metrics_endpoint_discovery import (
    MetricsEndpointChangeCharmEvents,
)
from ops.charm import CharmBase
from ops.model import ActiveStatus
from ops.testing import Harness


class _TestCharm(CharmBase):
    on = MetricsEndpointChangeCharmEvents()

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.metrics_endpoint_change, self._on_metrics_endpoint_change)

    def _on_metrics_endpoint_change(self, event):
        self.unit.status = ActiveStatus("metrics endpoints changed")


class TestMetricsEndpointDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(_TestCharm, meta="name: test-charm")

    def test_metrics_endpoint_change_event_emitted_handled(self):
        self.harness.begin()
        charm = self.harness.charm
        charm.on.metrics_endpoint_change.emit()
        self.assertEqual(charm.unit.status, ActiveStatus("metrics endpoints changed"))
