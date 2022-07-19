# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest import mock
from unittest.mock import Mock

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
                "placeholder",
                limits=None,
                requests=None,
            )

    def setUp(self) -> None:
        self.harness = Harness(
            self._TestCharm, meta=open("metadata.yaml"), config=open("config.yaml")
        )

    @mock.patch("lightkube.core.client.GenericSyncClient", Mock)
    @mock.patch(f"{CL_PATH}._namespace", "test-namespace")
    def test_listener_is_attached_for_config_changed_event(self):
        self.harness.begin()
        charm = self.harness.charm
        with mock.patch(f"{CL_PATH}._patch") as patch:
            charm.on.config_changed.emit()
            self.assertEqual(patch.call_count, 1)

    @mock.patch("lightkube.core.client.GenericSyncClient", Mock)
    @mock.patch(f"{CL_PATH}._namespace", "test-namespace")
    def test_patch_is_applied_regardless_of_leadership_status(self):
        self.harness.begin()
        charm = self.harness.charm
        for is_leader in (True, False):
            with self.subTest(is_leader=is_leader):
                self.harness.set_leader(True)
                with mock.patch(f"{CL_PATH}._patch") as patch:
                    charm.on.config_changed.emit()
                    self.assertEqual(patch.call_count, 1)

    @mock.patch.object(KubernetesComputeResourcesPatch, "_namespace", "test-namespace")
    @mock.patch(f"{CL_PATH}._is_patched", lambda *a, **kw: False)
    @mock.patch("lightkube.core.client.GenericSyncClient")
    def test_patch_is_applied_during_startup_sequence(self, client_mock):
        self.harness.begin_with_initial_hooks()
        self.assertGreater(client_mock.call_count, 0)

    @mock.patch.object(KubernetesComputeResourcesPatch, "_namespace", "test-namespace")
    @mock.patch(f"{CL_PATH}._is_patched", lambda *a, **kw: False)
    @mock.patch("lightkube.core.client.GenericSyncClient")
    def test_invalid_config_raises(self, client_mock):
        self.harness.begin_with_initial_hooks()
        with self.assertRaises(ValueError):
            self.harness.update_config({"cpuu": "1"})
        with self.assertRaises(ValueError):
            self.harness.update_config({"memoryy": "1Gi"})

        # TODO: [("-1", "1Gi"), ("1", "-1Gi"), ("4x", "1Gi"), ("1", "1Gx")]
