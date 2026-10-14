"""Steps about logs reaching Loki."""

import jubilant
from observability_clients import Loki
from pytest_bdd import given, parsers, then, when
from tenacity import retry, stop_after_delay, wait_fixed

from observability_steps._juju import ensure_deployed, ensure_integrated

LOKI_APP = "loki"
LOKI_PORT = 3100


@given("Loki is deployed")
def loki_is_deployed(juju: jubilant.Juju):
    ensure_deployed(juju, LOKI_APP, "loki-k8s", channel="dev/edge")


@given(parsers.parse('the "{application}" application is integrated with Loki'))
@when(parsers.parse('the "{application}" application is integrated with Loki'))
def integrated_with_loki(juju: jubilant.Juju, application: str):
    ensure_integrated(juju, application, f"{LOKI_APP}:logging")


@then(parsers.parse('Loki has logs from the "{application}" application'))
def loki_has_logs_from(juju: jubilant.Juju, application: str):
    address = juju.status().apps[LOKI_APP].units[f"{LOKI_APP}/0"].address
    _assert_has_logs(
        Loki(url=f"http://{address}:{LOKI_PORT}"),
        query=f'{{juju_application="{application}"}}',
    )


@retry(stop=stop_after_delay(5 * 60), wait=wait_fixed(15), reraise=True)
def _assert_has_logs(loki: Loki, *, query: str) -> None:
    # Log forwarding is periodic, so the first lines can land after the model settles.
    assert loki.has_log_line(query), f"Loki has no log lines matching {query}"
