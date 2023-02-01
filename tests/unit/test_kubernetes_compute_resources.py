# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest import mock
from unittest.mock import Mock

import yaml
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    adjust_resource_requirements,
    is_valid_spec,
    sanitize_resource_spec_dict,
)
from ops.charm import CharmBase
from ops.testing import Harness

from tests.unit.helpers import PROJECT_DIR

CL_PATH = "charms.observability_libs.v0.kubernetes_compute_resources_patch.KubernetesComputeResourcesPatch"


class TestKubernetesComputeResourcesPatch(unittest.TestCase):
    class _TestCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.resources_patch = KubernetesComputeResourcesPatch(
                self,
                "placeholder",
                resource_reqs_func=lambda: adjust_resource_requirements(None, None),
            )
            self.framework.observe(self.resources_patch.on.patch_failed, self._patch_failed)
            self.patch_failed_counter = 0

        def _patch_failed(self, _):
            self.patch_failed_counter += 1

    def setUp(self) -> None:
        with open(PROJECT_DIR / "config.yaml") as config_file:
            config = yaml.safe_load(config_file)
        self.harness = Harness(
            self._TestCharm, meta=open(PROJECT_DIR / "metadata.yaml"), config=str(config)
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
    @mock.patch("lightkube.core.client.GenericSyncClient")
    def test_patch_is_applied_during_startup_sequence(self, client_mock):
        self.harness.begin_with_initial_hooks()
        self.assertGreater(client_mock.call_count, 0)

    @mock.patch.object(KubernetesComputeResourcesPatch, "_namespace", "test-namespace")
    @mock.patch("lightkube.core.client.GenericSyncClient")
    def test_invalid_config_emits_custom_event(self, client_mock):
        self.harness.begin_with_initial_hooks()

        # Test invalid quantity values
        for cpu, memory in [
            ("-1", ""),
            ("", "-1Gi"),
            ("-1", "1Gi"),
            ("1", "-1Gi"),
            ("4x", "1Gi"),
            ("1", "1Gx"),
        ]:
            with self.subTest(cpu=cpu, memory=memory):
                before = self.harness.charm.patch_failed_counter
                self.harness.update_config({"cpu": cpu, "memory": memory})
                after = self.harness.charm.patch_failed_counter
                self.assertGreater(after, before)


class TestResourceSpecDictValidation(unittest.TestCase):
    def test_sanitize_resource_spec_dict(self):
        self.assertEqual(None, sanitize_resource_spec_dict(None))
        self.assertEqual({}, sanitize_resource_spec_dict({}))
        self.assertEqual({"bad": "combo"}, sanitize_resource_spec_dict({"bad": "combo"}))
        self.assertEqual({"cpu": 1}, sanitize_resource_spec_dict({"cpu": 1}))
        self.assertEqual({"cpu": "1"}, sanitize_resource_spec_dict({"cpu": "1"}))
        self.assertEqual({"memory": "858993460"}, sanitize_resource_spec_dict({"memory": "0.8Gi"}))

    def test_is_valid_spec(self):
        self.assertTrue(is_valid_spec(None))
        self.assertTrue(is_valid_spec({}))
        self.assertTrue(is_valid_spec({"cpu": "1"}))
        self.assertTrue(is_valid_spec({"memory": "858993460"}))
        self.assertTrue(is_valid_spec({"memory": "0.8Gi"}))
        self.assertTrue(is_valid_spec({"cpu": None, "memory": None}))

        self.assertFalse(is_valid_spec({"bad": "combo"}))
        self.assertFalse(is_valid_spec({"invalid-key": "1"}))
