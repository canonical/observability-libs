#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


"""A tester charm for the Observability libs."""

from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceSpecDict,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus


class ObservabilityLibsCharm(CharmBase):
    """Tester charm for Observability libs."""

    def __init__(self, *args):
        super().__init__(*args)

        self._container_name = "placeholder"

        resource_limit = ResourceSpecDict(
            cpu=self.model.config.get("cpu"),
            memory=self.model.config.get("memory"),
        )
        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            self._container_name,
            limits=resource_limit,
            requests=resource_limit,
        )
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        self._configure()
        # self.framework.observe(self.on.config_changed, self._configure)
        # self.framework.observe(self.on.placeholder_pebble_ready, self._configure)
        # self.framework.observe(self.on.start, self._configure)

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent):
        self.unit.status = BlockedStatus(event.message)

    def _configure(self):
        container = self.unit.get_container(self._container_name)

        if not self.resources_patch.is_ready():
            if isinstance(self.unit.status, ActiveStatus) or self.unit.status.message == "":
                self.unit.status = MaintenanceStatus(
                    "Waiting for resource limit patch to apply: limits={}, requests={}".format(
                        self.resources_patch.limits,
                        self.resources_patch.requests,
                    )
                )
            return

        if not container.can_connect():
            self.unit.status = MaintenanceStatus("Waiting for Pebble ready")
            return

        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(ObservabilityLibsCharm)
