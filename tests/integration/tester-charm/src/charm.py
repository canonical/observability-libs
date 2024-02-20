#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""Tester Charm."""

import logging

import ops
from charms.observability_libs.v1.cert_handler import CertHandler

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]

KEY_PATH = "/home/ubuntu/secrets/server.key"
CERT_PATH = "/home/ubuntu/secrets/server.cert"
CA_CERT_PATH = "/home/ubuntu/secrets/ca.cert"


class TesterCharm(ops.CharmBase):
    """Tester Charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = "httpbin"
        self._container = self.unit.get_container(self._name)
        self.cert_handler = CertHandler(
            charm=self,
            key="tester-server-cert",
            sans=["charm.tester"],
        )
        self.framework.observe(self.cert_handler.on.cert_changed, self._on_server_cert_changed)
        self.framework.observe(self.on["httpbin"].pebble_ready, self._on_httpbin_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)


    def _on_upgrade_charm(self, _):
        self._update_cert()

    def _on_server_cert_changed(self, _):
        self._update_cert()

    def _on_httpbin_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Define and start a workload using the Pebble API.

        Change this example to suit your needs. You'll need to specify the right entrypoint and
        environment configuration for your specific workload.

        Learn more about interacting with Pebble at at https://juju.is/docs/sdk/pebble.
        """
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Add initial Pebble config layer using the Pebble API
        container.add_layer("httpbin", self._pebble_layer, combine=True)
        # Make Pebble reevaluate its plan, ensuring any services are started if enabled.
        container.replan()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ops.ActiveStatus()

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle changed configuration.

        Change this example to suit your needs. If you don't need to handle config, you can remove
        this method.

        Learn more about config at https://juju.is/docs/sdk/config
        """
        # Fetch the new config value
        log_level = self.model.config["log-level"].lower()

        # Do some validation of the configuration option
        if log_level in VALID_LOG_LEVELS:
            # Verify that we can connect to the Pebble API in the workload container
            if self._container.can_connect():
                # Push an updated layer with the new config
                self._container.add_layer("httpbin", self._pebble_layer, combine=True)
                self._container.replan()

                logger.debug("Log level for gunicorn changed to '%s'", log_level)
                self.unit.status = ops.ActiveStatus()
            else:
                # We were unable to connect to the Pebble API, so we defer this event
                event.defer()
                self.unit.status = ops.WaitingStatus("waiting for Pebble API")
        else:
            # In this case, the config option is bad, so block the charm and notify the operator.
            self.unit.status = ops.BlockedStatus("invalid log level: '{log_level}'")

    @property
    def _pebble_layer(self) -> ops.pebble.LayerDict:
        """Return a dictionary representing a Pebble layer."""
        return {
            "summary": "httpbin layer",
            "description": "pebble config layer for httpbin",
            "services": {
                "httpbin": {
                    "override": "replace",
                    "summary": "httpbin",
                    "command": "gunicorn -b 0.0.0.0:80 httpbin:app -k gevent",
                    "startup": "enabled",
                    "environment": {
                        "GUNICORN_CMD_ARGS": f"--log-level {self.model.config['log-level']}"
                    },
                }
            },
        }

    def _is_cert_available(self) -> bool:
        return (
            self.cert_handler.enabled
            and (self.cert_handler.server_cert is not None)
            and (self.cert_handler.private_key is not None)
            and (self.cert_handler.ca_cert is not None)
        )

    def _update_cert(self):
        if not self._container.can_connect():
            return

        if self._is_cert_available():
            # Save the workload certificates
            self._container.push(
                CERT_PATH,
                self.cert_handler.server_cert,  # pyright: ignore
                make_dirs=True,
            )
            self._container.push(
                KEY_PATH,
                self.cert_handler.private_key,  # pyright: ignore
                make_dirs=True,
            )
            # Save the CA among the trusted CAs and trust it
            self._container.push(
                CA_CERT_PATH,
                self.cert_handler.ca_cert,  # pyright: ignore
                make_dirs=True,
            )


if __name__ == "__main__":  # pragma: nocover
    ops.main(TesterCharm)  # type: ignore
