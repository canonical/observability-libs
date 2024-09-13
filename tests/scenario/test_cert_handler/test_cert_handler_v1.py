import datetime
import json
import socket
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID
from ops import CharmBase
from scenario import Context, PeerRelation, Relation, State

from lib.charms.observability_libs.v1.cert_handler import (
    CertHandler,
)

libs = str(Path(__file__).parent.parent.parent.parent / "lib")
sys.path.append(libs)
MOCK_HOSTNAME = "mock-hostname"


class MyCharm(CharmBase):
    META = {
        "name": "fabio",
        "requires": {"certificates": {"interface": "certificates"}},
    }

    def __init__(self, fw):
        super().__init__(fw)
        sans = [socket.getfqdn()]
        if hostname := self._mock_san:
            sans.append(hostname)

        self.ch = CertHandler(self, key="ch", sans=sans, refresh_events=[self.on.config_changed])

    @property
    def _mock_san(self):
        """This property is meant to be mocked to return a mock string hostname to be used as SAN.

        By default, it returns None.
        """
        return None


def generate_certificate_and_key():
    """Generate certificate and CA to use for tests."""
    # Generate private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Generate CA certificate
    ca_subject = issuer = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(x509.NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Example CA"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, "example.com"),
        ]
    )

    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    # Generate server certificate
    server_subject = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(x509.NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Example Server"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, "server.example.com"),
        ]
    )

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_subject)
        .issuer_name(ca_subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("server.example.com")]), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )

    # Convert to PEM format
    ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    server_cert_pem = server_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    return ca_cert_pem, server_cert_pem, private_key_pem


def get_csr_obj(csr: str):
    return x509.load_pem_x509_csr(csr.encode(), default_backend())


def get_sans_from_csr(csr):
    san_extension = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    return set(san_extension.value.get_values_for_type(x509.DNSName))


@pytest.fixture
def ctx():
    return Context(MyCharm, MyCharm.META, juju_version="3.0.3")


@pytest.fixture
def certificates():
    return Relation("certificates")


@contextmanager
def _sans_patch(hostname=MOCK_HOSTNAME):
    with patch.object(MyCharm, "_mock_san", hostname):
        yield


@contextmanager
def _cert_renew_patch():
    with patch(
        "charms.tls_certificates_interface.v3.tls_certificates.TLSCertificatesRequiresV3.request_certificate_renewal"
    ) as patcher:
        yield patcher


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


def test_renew_csr_on_sans_change(ctx, certificates):
    # generate a CSR
    with ctx.manager(
        certificates.joined_event,
        State(leader=True, relations=[certificates]),
    ) as mgr:
        charm = mgr.charm
        state_out = mgr.run()
        orig_csr = get_csr_obj(charm.ch._csr)
        assert get_sans_from_csr(orig_csr) == {socket.getfqdn()}

    # trigger a config_changed with a modified SAN
    with _sans_patch():
        with ctx.manager("config_changed", state_out) as mgr:
            charm = mgr.charm
            state_out = mgr.run()
            csr = get_csr_obj(charm.ch._csr)
            # assert CSR contains updated SAN
            assert get_sans_from_csr(csr) == {socket.getfqdn(), MOCK_HOSTNAME}


def test_csr_no_change_on_wrong_refresh_event(ctx, certificates):
    with _cert_renew_patch() as renew_patch:
        with ctx.manager(
            "config_changed",
            State(leader=True, relations=[certificates]),
        ) as mgr:
            charm = mgr.charm
            state_out = mgr.run()
            orig_csr = get_csr_obj(charm.ch._csr)
            assert get_sans_from_csr(orig_csr) == {socket.getfqdn()}

    with _sans_patch():
        with _cert_renew_patch() as renew_patch:
            with ctx.manager("update_status", state_out) as mgr:
                charm = mgr.charm
                state_out = mgr.run()
                csr = get_csr_obj(charm.ch._csr)
                assert get_sans_from_csr(csr) == {socket.getfqdn()}
                assert renew_patch.call_count == 0


def test_csr_no_change(ctx, certificates):

    with ctx.manager(
        "config_changed",
        State(leader=True, relations=[certificates]),
    ) as mgr:
        charm = mgr.charm
        state_out = mgr.run()
        orig_csr = get_csr_obj(charm.ch._csr)
        assert get_sans_from_csr(orig_csr) == {socket.getfqdn()}

    with _cert_renew_patch() as renew_patch:
        with ctx.manager("config_changed", state_out) as mgr:
            charm = mgr.charm
            state_out = mgr.run()
            csr = get_csr_obj(charm.ch._csr)
            assert get_sans_from_csr(csr) == {socket.getfqdn()}
            assert renew_patch.call_count == 0


def test_chain_contains_server_cert(ctx, certificates):
    ca_cert_pem, server_cert_pem, _ = generate_certificate_and_key()

    certificates = certificates.replace(
        remote_app_data={
            "certificates": json.dumps(
                [
                    {
                        "certificate": server_cert_pem,
                        "ca": ca_cert_pem,
                        "chain": [ca_cert_pem],
                        "certificate_signing_request": "csr",
                    }
                ],
            )
        },
        local_unit_data={
            "certificate_signing_requests": json.dumps([{"certificate_signing_request": "csr"}])
        },
    )

    with ctx.manager("update_status", State(leader=True, relations=[certificates])) as mgr:
        mgr.run()
        assert server_cert_pem in mgr.charm.ch.chain
        assert x509.load_pem_x509_certificate(mgr.charm.ch.chain.encode(), default_backend())
