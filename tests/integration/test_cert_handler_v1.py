# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import subprocess
from pathlib import Path

import pytest
import yaml
from helpers import get_secret
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./tests/integration/tester-charm/metadata.yaml").read_text())
APP_NAME = METADATA["name"]

KEY_PATH = "/home/ubuntu/secrets/server.key"
CERT_PATH = "/home/ubuntu/secrets/server.cert"
CA_CERT_PATH = "/home/ubuntu/secrets/ca.cert"


@pytest.mark.abort_on_fail
async def test_cert_handler_v1(
    ops_test: OpsTest,
    tester_charm: Path,
):
    """Validate the integration between TesterCharm and self-signed-certificates using CertHandler v1."""
    assert ops_test.model
    assert ops_test.model_full_name
    ca_app_name = "ca"
    apps = [APP_NAME, ca_app_name]

    image = METADATA["resources"]["httpbin-image"]["upstream-source"]
    resources = {"httpbin-image": image}

    await asyncio.gather(
        ops_test.model.deploy(
            "self-signed-certificates",
            application_name=ca_app_name,
            channel="latest/beta",
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
    for path in [KEY_PATH, CERT_PATH, CA_CERT_PATH]:
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


@pytest.mark.abort_on_fail
async def test_secrets_does_not_change_after_refresh(ops_test: OpsTest, tester_charm: Path):
    assert ops_test.model
    paths = [KEY_PATH, CERT_PATH, CA_CERT_PATH]
    secrets = {paths[0]: "", paths[1]: "", paths[2]: ""}

    for path in paths:
        secrets[path] = get_secret(ops_test, APP_NAME, path)

    application = ops_test.model.applications[APP_NAME]
    assert application
    await application.refresh(path=tester_charm)
    await ops_test.model.wait_for_idle(
        status="active", raise_on_error=False, timeout=600, idle_period=30
    )

    for path in paths:
        assert secrets[path] == get_secret(ops_test, APP_NAME, path)


@pytest.mark.abort_on_fail
async def test_change_ssc_and_tester_still_have_certs(ops_test: OpsTest):
    assert ops_test.model
    assert ops_test.model_full_name
    await ops_test.model.remove_application("ca", block_until_done=True)
    await asyncio.gather(
        ops_test.model.deploy(
            "self-signed-certificates",
            application_name="ca2",
            channel="latest/beta",
            trust=True,
        ),
    )
    # wait for all charms to be active
    await ops_test.model.wait_for_idle(
        apps=["ca2", APP_NAME], status="active", wait_for_exact_units=1
    )
    logger.info("All services active")

    await ops_test.model.add_relation(APP_NAME, "ca2")
    logger.info("Relations issued")
    await ops_test.model.wait_for_idle(
        apps=["ca2", APP_NAME], status="active", wait_for_exact_units=1
    )
    # Check the certs files are in the filesystem
    for path in [KEY_PATH, CERT_PATH, CA_CERT_PATH]:
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

    # TODO: Fix tester charm to use listen HTTPS when the relation to ssc is established
    # and then curl HTTPS url to check if everything is working.
