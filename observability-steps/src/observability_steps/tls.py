"""Steps about applications serving their API over TLS."""

import socket
import ssl

import jubilant
from pytest_bdd import given, parsers, then, when
from tenacity import retry, stop_after_delay, wait_fixed

from observability_steps._juju import ensure_deployed, ensure_integrated

CA_APP = "ca"


@given("a certificates provider is deployed")
def a_certificates_provider_is_deployed(juju: jubilant.Juju):
    ensure_deployed(juju, CA_APP, "self-signed-certificates", channel="1/stable")


@given(
    parsers.parse('the "{application}" application is integrated with the certificates provider')
)
@when(
    parsers.parse('the "{application}" application is integrated with the certificates provider')
)
def integrated_with_the_certificates_provider(juju: jubilant.Juju, application: str):
    ensure_integrated(juju, application, f"{CA_APP}:certificates")


@then(parsers.parse('the "{application}" application serves HTTPS on port {port:d}'))
def serves_https(juju: jubilant.Juju, application: str, port: int):
    """Every unit completes a TLS handshake whose certificate chains to the CA and names the unit."""
    ca = juju.run(f"{CA_APP}/0", "get-ca-certificate").results["ca-certificate"]
    context = ssl.create_default_context(cadata=ca)
    status = juju.status()
    for unit, unit_status in status.apps[application].units.items():
        fqdn = f"{unit.replace('/', '-')}.{application}-endpoints.{status.model.name}.svc.cluster.local"
        _handshake(context, address=unit_status.address, port=port, hostname=fqdn)


@retry(stop=stop_after_delay(120), wait=wait_fixed(10), reraise=True)
def _handshake(context: ssl.SSLContext, *, address: str, port: int, hostname: str) -> None:
    # The workload may still be restarting with its new certificate after the model settles.
    with (
        socket.create_connection((address, port), timeout=10) as sock,
        context.wrap_socket(sock, server_hostname=hostname),
    ):
        pass
