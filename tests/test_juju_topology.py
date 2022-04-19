# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from collections import OrderedDict

from charms.observability_libs.v0.juju_topology import JujuTopology
from ops.charm import CharmBase
from ops.testing import Harness


class JujuTopologyCharm(CharmBase):
    pass


class TestJujuTopologyLib(unittest.TestCase):
    def setUp(self):
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

    def test_dict_includes_all_expected_keys(self):
        self.assertEqual(self.topology.as_dict(), self.input)

    def test_dict_does_not_include_excluded(self):
        expected = self.input.copy()
        expected = _filter_dict(expected, ["unit"])
        self.assertEqual(self.topology.as_dict(excluded_keys=["unit"]), expected)

    def test_dict_handles_remapping(self):
        expected = OrderedDict(
            ("name", v) if k == "charm_name" else (k, v) for k, v in self.input.items()
        )
        self.assertEqual(
            self.topology.as_dict(remapped_keys={"charm_name": "name"}),
            expected,
        )

    def test_identifier_omits_unit(self):
        expected = self.input.copy()
        expected = _filter_dict(expected, ["unit", "charm_name"])
        expected["model_uuid"] = expected["model_uuid"][:7]

        self.assertEqual(
            self.topology.identifier,
            "_".join([v for _, v in expected.items() if v]),
        )

    def test_label_matchers_dict_prefixes_keys(self):
        expected = OrderedDict(
            ("juju_{}".format("charm" if key == "charm_name" else key), val)
            for key, val in self.input.items()
        )
        expected = _filter_dict(expected, ["juju_unit"])

        self.assertEqual(self.topology.prefixed_dict, expected)

    def test_label_matchers_creates_a_valid_matcher(self):
        prefixed = OrderedDict(
            ("juju_{}".format("charm" if raw_key == "charm_name" else raw_key), raw_val)
            for raw_key, raw_val in self.input.items()
        )
        prefixed = _filter_dict(prefixed, ["juju_unit"])
        expected = ", ".join('{}="{}"'.format(key, value) for key, value in prefixed.items())
        self.assertEqual(expected, self.topology.label_matchers)

    def test_from_charm(self):
        self.harness = Harness(JujuTopologyCharm, meta="name: {}".format(self.input["charm_name"]))
        self.harness.set_model_name(self.input["model"])
        self.harness.set_model_uuid(self.input["model_uuid"])
        self.harness.begin()

        topology = JujuTopology.from_charm(self.harness.charm)
        self.assertEqual(topology.as_dict(), self.input)

    def test_from_dict(self):
        topology = JujuTopology.from_dict(self.input)
        self.assertEqual(topology.as_dict(), self.input)


def _filter_dict(labels, excluded_keys):
    return OrderedDict({k: v for k, v in labels.items() if k not in excluded_keys})
