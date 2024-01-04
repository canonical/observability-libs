# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import subprocess
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./tests/integration/tester-charm/metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_cert_handler_v1(
    ops_test: OpsTest,
    tester_charm: Path,
):
    """Validate the integration between TesterCharm and self-signed-certificates using CertHandler v1."""
    ca_app_name = "ca"
    apps = [APP_NAME, ca_app_name]

    image = METADATA["resources"]["httpbin-image"]["upstream-source"]
    resources = {"httpbin-image": image}

    await asyncio.gather(
        ops_test.model.deploy(
            "self-signed-certificates",
            application_name=ca_app_name,
            channel="beta",
            trust=True,
        ),
        ops_test.model.deploy(
            tester_charm,
            resources=resources,
            application_name=APP_NAME,
        ),
    )
    logger.info("All services deployed")

    # wait for all charms to be active
    await ops_test.model.wait_for_idle(apps=apps, status="active", wait_for_exact_units=1)
    logger.info("All services active")

    await ops_test.model.add_relation(APP_NAME, ca_app_name)
    logger.info("Relations issued")
    await ops_test.model.wait_for_idle(apps=apps, status="active", wait_for_exact_units=1)

    # Check the certs files are in the filesystem
    for path in ["/tmp/server.key", "/tmp/server.cert", "/tmp/ca.cert"]:
        assert 0 == subprocess.check_call(
            [
                "juju",
                "ssh",
                "--model",
                ops_test.model_full_name,
                "--container",
                "httpbin",
                f"{APP_NAME}/0",
                f"ls {path}",
            ]
        )
