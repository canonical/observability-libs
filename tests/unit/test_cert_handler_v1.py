# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch
from textwrap import dedent

from charms.observability_libs.v1.cert_handler import CertHandler
from ops.charm import CharmBase
from ops.model import ActiveStatus
from ops.testing import Harness


class StandInCharm(CharmBase):
    meta = dedent("""
            name: test-charm
            peers:
              peers:
                interface: peers
            requires:
              certificates:
                interface: tls-certificates
                limit: 1
        """)

    def __init__(self, *args):
        super().__init__(*args)

        self.cert_handler = CertHandler(
            charm=self,
            key="stand-in-server-cert",
            sans=["demo.example.internal"],
        )

        self.framework.observe(self.cert_handler.on.cert_changed, self._on_server_cert_changed)

    def _on_server_cert_changed(self, event):
        self.unit.status = ActiveStatus("metrics endpoints changed")


class TestCertHandlerV1(unittest.TestCase):

    def setUp(self) -> None:
        self.harness = Harness(StandInCharm, meta=StandInCharm.meta)
        self.harness.begin_with_initial_hooks()

    def test_tls_is_inactive(self):
        # GIVEN an isolated charm
        charm = self.harness.charm

        # THEN private key is ready, but the CSR isn't
        self.assertIn("-----BEGIN RSA PRIVATE KEY-----", charm.cert_handler.private_key)
        self.assertEqual(charm.cert_handler._csr, None)

        # AND the "enabled" and "available" properties are both False
        self.assertEqual(charm.cert_handler.enabled, False)
        self.assertEqual(charm.cert_handler.available, False)

        # WHEN a certificates relations just joins
        self.relation_id = self.harness.add_relation("certificates", "ca")
        self.harness.add_relation_unit(self.relation_id, "ca/0")

        # THEN the CSR is ready, tls is "enabled" but not "available"
        self.assertIn("-----BEGIN CERTIFICATE REQUEST-----", charm.cert_handler._csr)
        self.assertEqual(charm.cert_handler.enabled, True)
        self.assertEqual(charm.cert_handler.available, False)

    def test_custom_event_emitted_when_certificates_relation_removed(self):
        # GIVEN a tls relation
        charm = self.harness.charm
        self.relation_id = self.harness.add_relation("certificates", "ca")
        self.harness.add_relation_unit(self.relation_id, "ca/0")

        # WHEN the relation is removed
        observer_patcher = patch.object(charm, "_on_server_cert_changed")
        mock = observer_patcher.start()
        self.harness.remove_relation(self.relation_id)

        # THEN the "cert changed" observer is called
        mock.assert_called_once()
