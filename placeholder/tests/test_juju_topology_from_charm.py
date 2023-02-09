# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from collections import OrderedDict

import ops
from ops.charm import CharmBase
from ops.testing import Harness

from jo11y.juju_topology import JujuTopology


class JujuTopologyCharm(CharmBase):
    pass


class TestJujuTopology(unittest.TestCase):
    def setUp(self):
        ops.testing.SIMULATE_CAN_CONNECT = True  # type: ignore
        self.input = OrderedDict(
            [
                ("model", "some-model"),
                ("model_uuid", "00000000-0000-4000-8000-000000000000"),
                ("application", "test-application"),
                ("unit", "test-application/0"),
                ("charm_name", "test-application"),
            ]
        )
        self.topology = JujuTopology(
            self.input["model"],
            self.input["model_uuid"],
            self.input["application"],
            self.input["unit"],
            self.input["charm_name"],
        )

    def test_from_charm(self):
        self.harness = Harness(JujuTopologyCharm, meta=f"name: {self.input['charm_name']}")
        self.harness.set_model_name(self.input["model"])
        self.harness.set_model_uuid(self.input["model_uuid"])
        self.harness.begin()

        topology = JujuTopology.from_charm(self.harness.charm)
        self.assertEqual(topology.as_dict(), self.input)
