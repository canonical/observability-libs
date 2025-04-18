#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests resource limits on startup and after config-changed."""

import logging
from pathlib import Path

import pytest
import yaml
from lightkube import Client
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = METADATA["name"]
container_name = "placeholder"
resources = {"placeholder-image": METADATA["resources"]["placeholder-image"]["upstream-source"]}

# GitHub runner is 2cpu7gb and occasionally times out when using 300 sec.
deploy_timeout = 600
resched_timeout = 600

default_limits = None


def get_podspec(ops_test: OpsTest, app_name: str, container_name: str):
    assert ops_test.model_name
    client = Client()
    pod = client.get(Pod, name=f"{app_name}-0", namespace=ops_test.model_name)
    podspec = next(iter(filter(lambda ctr: ctr.name == container_name, pod.spec.containers)))  # type: ignore
    return podspec


async def test_setup_env(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, o11y_libs_charm):
    """Build the charm-under-test and deploy it."""
    assert ops_test.model
    await ops_test.model.deploy(
        o11y_libs_charm,
        resources=resources,
        application_name=app_name,
        series="focal",
        trust=True,
    )

    await ops_test.model.wait_for_idle(status="active", timeout=deploy_timeout)


@pytest.mark.abort_on_fail
async def test_default_resource_limits_applied(ops_test: OpsTest):
    podspec = get_podspec(ops_test, app_name, container_name)
    # TODO use `equals_canonically` when becomes available
    assert podspec.resources
    assert podspec.resources.limits is None
    assert podspec.resources.requests is None


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("cpu,memory", [("500m", "0.15Gi"), ("0.30000000000000004", "0.15G")])
async def test_resource_limits_match_config(ops_test: OpsTest, cpu, memory):
    assert ops_test.model
    custom_limits = {"cpu": cpu, "memory": memory}
    application = ops_test.model.applications[app_name]
    assert application
    await application.set_config(custom_limits)
    await ops_test.model.wait_for_idle(
        status="active", timeout=resched_timeout, raise_on_error=False
    )
    await ops_test.model.wait_for_idle(status="active")

    # Not comparing limits (for now) because the strings may differ (0.9G vs 900M)
    # Comparison is done inside the k8s resource patch lib.


@pytest.mark.abort_on_fail
async def test_default_resource_limits_applied_after_resetting_config(ops_test: OpsTest):
    assert ops_test.model
    application = ops_test.model.applications[app_name]
    assert application
    await application.reset_config(["cpu", "memory"])
    await ops_test.model.wait_for_idle(status="active", timeout=resched_timeout)

    podspec = get_podspec(ops_test, app_name, container_name)
    assert podspec.resources
    assert podspec.resources.limits is None
    assert podspec.resources.requests is None
