# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest import mock

from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
)
from ops.charm import CharmBase
from ops.testing import Harness

CL_PATH = "charms.observability_libs.v0.kubernetes_compute_resources_patch.KubernetesComputeResourcesPatch"


class TestKubernetesComputeResourcesPatch(unittest.TestCase):
    class _TestCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.resources_patch = KubernetesComputeResourcesPatch(
                self,
                "container-name",
                limits=None,
                requests=None,
            )

    def setUp(self) -> None:
        self.harness = Harness(self._TestCharm, meta="name: test-charm")
        self.harness.begin()

    def test_listener_is_attached_for_default_and_refresh_events(self):
        charm = self.harness.charm
        with mock.patch(f"{CL_PATH}._patch") as patch:
            charm.on.config_changed.emit()
            self.assertEqual(patch.call_count, 1)

    def test_patch_is_applied_regardless_of_leadership_status(self):
        charm = self.harness.charm
        for is_leader in (True, False):
            with self.subTest(is_leader=is_leader):
                self.harness.set_leader(True)
                with mock.patch(f"{CL_PATH}._patch") as patch:
                    charm.on.config_changed.emit()
                    self.assertEqual(patch.call_count, 1)
