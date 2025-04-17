# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper functions for writing tests."""

import subprocess

from pytest_operator.plugin import OpsTest


def get_secret(ops_test: OpsTest, app_name: str, path: str) -> str:
    assert ops_test.model_full_name
    return subprocess.check_output(
        [
            "juju",
            "ssh",
            "--model",
            ops_test.model_full_name,
            "--container",
            "httpbin",
            f"{app_name}/0",
            "cat",
            path,
        ]
    ).decode()
