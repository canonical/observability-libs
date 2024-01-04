#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest

CERTHANDLER_PATH = "lib/charms/observability_libs/v1/cert_handler.py"
TESTINGCHARM_PATH = "tests/integration/tester-charm"

logger = logging.getLogger(__name__)


class Store(defaultdict):
    def __init__(self):
        super(Store, self).__init__(Store)

    def __getattr__(self, key):
        """Override __getattr__ so dot syntax works on keys."""
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        """Override __setattr__ so dot syntax works on keys."""
        self[key] = value


store = Store()


def timed_memoizer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        fname = func.__qualname__
        logger.info("Started: %s" % fname)
        start_time = datetime.now()
        if fname in store.keys():
            ret = store[fname]
        else:
            logger.info("Return for {} not cached".format(fname))
            ret = await func(*args, **kwargs)
            store[fname] = ret
        logger.info("Finished: {} in: {} seconds".format(fname, datetime.now() - start_time))
        return ret

    return wrapper


@pytest.fixture(scope="module")
@timed_memoizer
async def o11y_libs_charm(ops_test):
    """The charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="module")
@timed_memoizer
async def tester_charm(ops_test: OpsTest) -> Path:
    """A tester charm to integration test the CertHandler lib."""
    # Clean libs
    shutil.rmtree(f"{TESTINGCHARM_PATH}/lib", ignore_errors=True)

    # Link to lib
    dest_charmlib = Path(f"{TESTINGCHARM_PATH}/{CERTHANDLER_PATH}")
    dest_charmlib.parent.mkdir(parents=True)
    dest_charmlib.hardlink_to(CERTHANDLER_PATH)

    # fetch tls_certificates lib
    fetch_tls_cmd = [
        "charmcraft",
        "fetch-lib",
        "charms.tls_certificates_interface.v2.tls_certificates",
    ]
    await ops_test.run(*fetch_tls_cmd)
    shutil.move("lib/charms/tls_certificates_interface", f"{TESTINGCHARM_PATH}/lib/charms/")

    # build the charm
    clean_cmd = ["charmcraft", "clean", "-p", TESTINGCHARM_PATH]
    await ops_test.run(*clean_cmd)
    charm = await ops_test.build_charm(TESTINGCHARM_PATH)

    # clean libs
    shutil.rmtree(f"{TESTINGCHARM_PATH}/lib")
    return charm
