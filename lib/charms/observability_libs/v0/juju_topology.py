# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""## Overview.

This document explains how to use the JujuTopology class to
create and consume topology information in a consistent manner.

The goal of the Juju topology is to uniquely identify a piece
of software running across any of your Juju-managed deployments.
This is achieved by combining the following four elements:

- Model name
- Model UUID
- Application Name
- Unit Identifier

and in some cases, the charm name.

For a more in-depth description of the concept, as well as a
walk-through of it's use-case in observability, see
[this blog post](https://juju.is/blog/model-driven-observability-part-2-juju-topology-metrics)
on the Juju blog.

## Library Usage

This library may be used to create and consume JujuTopology objects.
The JujuTopology class provides three ways to create instances:

### Using the `from_charm` method

Enables instantiation by supplying the charm as an argument. When
creating topology objects for the current charm, this is the recommended
approach.

```python
topology = JujuTopology.from_charm(self)
```

### Using the `from_dict` method

Allows for instantion using a dictionary of relation data, like the
`scrape_metadata` from Prometheus or the labels of an alert rule. When
creating topology objects for remote charms, this is the recommended
approach.

```python
scrape_metadata = json.loads(relation.data[relation.app].get("scrape_metadata", "{}"))
topology = JujuTopology.from_dict(scrape_metadata)
```

### Using the class constructor

Enables instantiation using whatever values you want. While this
is useful in some very specific cases, this should not be considered
the least favored approach.

```python
topology = JujuTopology(
    model="some-juju-model",
    model_uuid="00000000-0000-0000-0000-000000000001",
    application="fancy-juju-application",
    unit="fancy-juju-application/0",
    charm_name="fancy-juju-application-k8s",
)
```

"""

from collections import OrderedDict
from typing import Dict, List, Optional

# The unique Charmhub library identifier, never change it
LIBID = "bced1658f20f49d28b88f61f83c2d232"

LIBAPI = 0
LIBPATCH = 1


class JujuTopology:
    """JujuTopology is used for storing, generating and formatting juju topology information."""

    def __init__(
        self,
        model: str,
        model_uuid: str,
        application: str,
        unit: Optional[str] = "",
        charm_name: Optional[str] = "",
    ):
        """Build a JujuTopology object.

        A `JujuTopology` object is used for storing and transforming
        Juju Topology information. This information is used to
        annotate Prometheus scrape jobs and alert rules. Such
        annotation when applied to scrape jobs helps in identifying
        the source of the scrapped metrics. On the other hand when
        applied to alert rules topology information ensures that
        evaluation of alert expressions is restricted to the source
        (charm) from which the alert rules were obtained.

        Args:
            model: a string name of the Juju model
            model_uuid: a globally unique string identifier for the Juju model
            application: an application name as a string
            unit: a unit name as a string
            charm_name: name of charm as a string
        """
        self.model = model
        self.model_uuid = model_uuid
        self.application = application
        self.charm_name = charm_name
        self.unit = unit

    @classmethod
    def from_charm(cls, charm):
        """Creates a JujuTopology instance by using the model data available on a charm object.

        Args:
            charm: a `CharmBase` object for which the `JujuTopology` will be constructed
        Returns:
            a `JujuTopology` object.
        """
        return cls(
            model=charm.model.name,
            model_uuid=charm.model.uuid,
            application=charm.model.app.name,
            unit=charm.model.unit.name,
            charm_name=charm.meta.name,
        )

    @classmethod
    def from_dict(cls, data: dict):
        """Factory method for creating `JujuTopology` children from a dictionary.

        Args:
            data: a dictionary with five keys providing topology information. The keys are
                - "model"
                - "model_uuid"
                - "application"
                - "unit"
                - "charm_name"
                `unit` and `charm_name` may be empty, but will result in more limited
                labels. However, this allows us to support payload-only charms.

        Returns:
            a `JujuTopology` object.
        """
        return cls(
            model=data["model"],
            model_uuid=data["model_uuid"],
            application=data["application"],
            unit=data.get("unit", ""),
            charm_name=data.get("charm_name", ""),
        )

    def as_dict(
        self,
        *,
        remapped_keys: Dict[str, str] = {},
        excluded_keys: List[str] = [],
        uuid_length: Optional[int] = None,
    ) -> OrderedDict:
        """Format the topology information into an ordered dict.

        Keeping the dictionary ordered is important to be able to
        compare dicts without having to resort to deep comparisons.

        Args:
            remapped_keys: A dictionary mapping old key names to new key names,
                which will be substituted when invoked.
            excluded_keys: A list of key names to exclude from the returned dict.
            uuid_length: The length to crop the UUID to.
        """
        model_uuid = self.model_uuid[: uuid_length - 1] if uuid_length else self.model_uuid
        ret = OrderedDict(
            [
                ("model", self.model),
                ("model_uuid", model_uuid),
                ("application", self.application),
                ("unit", self.unit),
                ("charm_name", self.charm_name),
            ]
        )

        for exclusion in excluded_keys:
            if exclusion in ret:
                ret.pop(exclusion)

        if remapped_keys:
            ret = OrderedDict(
                (remapped_keys.get(k), v) if remapped_keys.get(k) else (k, v) for k, v in ret.items()  # type: ignore
            )

        return ret

    def as_identifier(self) -> str:
        """Format the topology information into a terse string.

        This crops the model UUID, making it not suitable for comparisons against
        anything but other identifiers.
        """
        values = self.as_dict(
            excluded_keys=["unit", "charm_name"],
            uuid_length=8,
        ).values()

        return "_".join([str(val) for val in values]).replace("/", "_")

    def as_relabelled_dict(self):
        """Format the topology information into a dict with keys having 'juju_' as prefix.

        Relabelled topology never includes the unit as it would then only match
        the leader unit (ie. the unit that produced the dict).
        """
        items = self.as_dict(
            remapped_keys={"charm_name": "charm"},
            excluded_keys=["unit"],
        ).items()

        return {"juju_{}".format(key): value for key, value in items if value}

    def as_label_matchers(self) -> str:
        """Format the topology information into a verbose string.

        Topology label matchers should never include the unit as it
        would then only match the leader unit (ie. the unit that
        produced the matchers).
        """
        items = self.as_relabelled_dict().items()
        return ", ".join(['{}="{}"'.format(key, value) for key, value in items if value])
