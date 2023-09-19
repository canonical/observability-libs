import sys
from pathlib import Path

import pytest
from ops import CharmBase
from scenario import Context, PeerRelation, Relation, State

libs = str(Path(__file__).parent.parent.parent.parent / "lib")
sys.path.append(libs)

from lib.charms.observability_libs.v0.cert_handler import CertHandler  # noqa E402


class MyCharm(CharmBase):
    META = {
        "name": "fabio",
        "requires": {"certificates": {"interface": "certificates"}},
        "peers": {"replicas": {"interface": "replicas"}},
    }

    def __init__(self, fw):
        super().__init__(fw)
        self.ch = CertHandler(self, key="ch", peer_relation_name="replicas")


@pytest.fixture
def ctx():
    return Context(MyCharm, MyCharm.META)


@pytest.fixture
def peer():
    return PeerRelation("replicas")


@pytest.fixture
def certificates():
    return Relation("certificates")


def test_cert_joins(ctx, peer, certificates):
    # both peer and certificates are there, we're processing certificates-joined
    with ctx.manager(certificates.joined_event, State(relations=[peer, certificates])) as runner:
        runner.run()
        assert runner.charm.ch._private_key


def test_peer_created(ctx, peer, certificates):
    # both peer and certificates are there, we're processing peer-created
    with ctx.manager(peer.created_event, State(relations=[peer, certificates])) as runner:
        runner.run()
        assert runner.charm.ch._private_key
