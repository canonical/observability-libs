import socket
import sys
from pathlib import Path

import pytest
from ops import CharmBase
from scenario import Context, PeerRelation, Relation, State

from lib.charms.observability_libs.v1.cert_handler import (
    CertHandler,
)

libs = str(Path(__file__).parent.parent.parent.parent / "lib")
sys.path.append(libs)


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
        certificates.joined_event, State(leader=leader, relations=[certificates], secrets=[])
    ) as mgr:
        mgr.run()
        assert mgr.charm.ch.private_key


class MyJuju2Charm(CharmBase):
    META = {
        "name": "fabio",
        "requires": {"certificates": {"interface": "certificates"}},
        "peers": {"myfunkypeers": {"interface": "peerymcpeer"}},
    }

    def __init__(self, fw):
        super().__init__(fw)
        self.ch = CertHandler(
            self, key="ch", sans=[socket.getfqdn()], peer_relation_name="myfunkypeers"
        )


@pytest.fixture
def ctx_juju2():
    return Context(MyJuju2Charm, MyJuju2Charm.META, juju_version="2.0")


@pytest.mark.parametrize("leader", (True, False))
def test_cert_joins_peer_vault_backend(ctx_juju2, certificates, leader):
    with ctx_juju2.manager(
        certificates.joined_event,
        State(leader=leader, relations=[certificates, PeerRelation("myfunkypeers")], secrets=[]),
    ) as mgr:
        mgr.run()
        assert mgr.charm.ch.private_key
