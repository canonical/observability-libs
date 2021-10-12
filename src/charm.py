#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


"""A placeholder charm for the Observability libs."""

from ops.charm import CharmBase
from ops.main import main


class ObservabilityLibsCharm(CharmBase):
    """Placeholder charm for Observability libs."""

    pass


if __name__ == "__main__":
    main(ObservabilityLibsCharm)
