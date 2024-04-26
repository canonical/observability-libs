import socket
import sys
from pathlib import Path

import pytest
from ops import CharmBase
from scenario import Context, Relation, State

libs = str(Path(__file__).parent.parent.parent.parent / "lib")
sys.path.append(libs)

from lib.charms.observability_libs.v1.cert_handler import CertHandler  # noqa E402


class MyCharm(CharmBase):
    META = {
        "name": "fabio",
        "requires": {"certificates": {"interface": "certificates"}},
    }

    def __init__(self, fw):
        super().__init__(fw)

        self.ch = CertHandler(self, key="ch", sans=[socket.getfqdn()])


@pytest.fixture
def ctx():
    return Context(MyCharm, MyCharm.META, juju_version="3.0.3")


@pytest.fixture
def certificates():
    return Relation("certificates")


@pytest.mark.parametrize("leader", (True, False))
def test_cert_joins(ctx, certificates, leader):
    with ctx.manager(
        certificates.joined_event, State(leader=leader, relations=[certificates])
    ) as mgr:
        mgr.run()
        assert mgr.charm.ch.private_key
