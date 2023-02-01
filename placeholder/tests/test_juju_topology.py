# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
import uuid
from collections import OrderedDict

from jo11y.juju_topology import InvalidUUIDError, JujuTopology


class TestJujuTopology(unittest.TestCase):
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
        expected["model_uuid"] = expected["model_uuid"][:8]

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

        self.assertEqual(self.topology.label_matcher_dict, expected)

    def test_label_matchers_creates_a_valid_matcher(self):
        expected = 'juju_model="some-model", juju_model_uuid="00000000-0000-4000-8000-000000000000", juju_application="test-application", juju_charm="test-application"'
        self.assertEqual(expected, self.topology.label_matchers)

    def test_from_dict(self):
        topology = JujuTopology.from_dict(self.input)
        self.assertEqual(topology.as_dict(), self.input)

    def test_invalid_uuid(self):
        """Test invalid UUIDs that doesn't match the regex we use."""
        t_uuid = str(uuid.uuid4()).split("-")
        block1 = t_uuid[0]
        block2 = t_uuid[1]
        block3 = t_uuid[2]
        block4 = t_uuid[3]
        block5 = t_uuid[4]
        sep = "-"

        invalid_uuids = [
            # Invalid character in each block
            sep.join([block1[:-1] + "ñ", block2, block3, block4, block5]),
            sep.join([block1, block2[:-1] + "ñ", block3, block4, block5]),
            sep.join([block1, block2, block3[:-1] + "ñ", block4, block5]),
            sep.join([block1, block2, block3, block4[:-1] + "ñ", block5]),
            sep.join([block1, block2, block3, block4, block5[:-1] + "ñ"]),
            # More characters in each block
            sep.join([block1 + "a", block2, block3, block4, block5]),
            sep.join([block1, block2 + "a", block3, block4, block5]),
            sep.join([block1, block2, block3 + "a", block4, block5]),
            sep.join([block1, block2, block3, block4 + "a", block5]),
            sep.join([block1, block2, block3, block4, block5 + "a"]),
            # Less characters in each block
            sep.join([block1[:-1], block2, block3, block4, block5]),
            sep.join([block1, block2[:-1], block3, block4, block5]),
            sep.join([block1, block2, block3[:-1], block4, block5]),
            sep.join([block1, block2, block3, block4[:-1], block5]),
            sep.join([block1, block2, block3, block4, block5[:-1]]),
            # More than one - in separator
            (sep * 2).join([block1, block2, block3, block4, block5]),
            # Missing blocks
            sep.join([block2, block3, block4, block5]),
            sep.join([block1, block3, block4, block5]),
            sep.join([block1, block2, block4, block5]),
            sep.join([block1, block2, block3, block5]),
            sep.join([block1, block2, block3, block4]),
            # UUID v4 validation.
            # 1st position in block3 must start with 4
            sep.join([block1, block2, "5" + block3[1:], block4, block5]),
            # 1st position in block4 must start with a, b, 8 or 9
            sep.join([block1, block2, block3, "w" + block4[1:], block5]),
            # UUID v1
            str(uuid.uuid1()),
            # UUID v5
            str(uuid.uuid5(uuid.NAMESPACE_DNS, "juju.is")),
        ]

        for invalid_uuid in invalid_uuids:
            topology_invalid_uuid = OrderedDict(
                [
                    ("model", "some-model"),
                    ("model_uuid", invalid_uuid),
                    ("application", "test-application"),
                    ("unit", "test-application/0"),
                    ("charm_name", "test-application"),
                ]
            )
            with self.assertRaises(InvalidUUIDError) as context:
                JujuTopology.from_dict(topology_invalid_uuid)

            self.assertEqual(f"'{invalid_uuid}' is not a valid UUID.", str(context.exception))


def _filter_dict(labels, excluded_keys):
    return OrderedDict({k: v for k, v in labels.items() if k not in excluded_keys})
