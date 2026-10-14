# observability-steps

Shared [pytest-bdd](https://pytest-bdd.readthedocs.io/) step definitions for Observability charm and solution tests. Suites write their own feature files, in their own words, and reuse these sentences for behaviours common to Observability charms.

> Spike for TAP-1149: evaluates sharing step definitions while each charm owns its feature files.

## Vocabulary

| Module | Sentences |
|---|---|
| `observability_steps.tls` | `a certificates provider is deployed`<br>`the "<app>" application is integrated with the certificates provider`<br>`the "<app>" application serves HTTPS on port <port>` |
| `observability_steps.logs` | `Loki is deployed`<br>`the "<app>" application is integrated with Loki`<br>`Loki has logs from the "<app>" application` |

`tests/vocabulary.feature` uses every sentence, and the test suite fails if one of them has no definition.

## Usage

Register the modules in the suite's top-level `conftest.py`; steps also need a `juju` fixture (`jubilant.Juju`), e.g. from `pytest-jubilant`:

```python
pytest_plugins = ["observability_steps.tls", "observability_steps.logs"]
```

Then use the sentences in the suite's own feature files:

```gherkin
Feature: TLS
  Alertmanager serves its API over HTTPS once integrated with a certificates provider.

  Scenario: Alertmanager serves its API over HTTPS
    Given the "alertmanager" application is deployed
    And a certificates provider is deployed
    When the "alertmanager" application is integrated with the certificates provider
    Then the "alertmanager" application serves HTTPS on port 9093
```

Deploying the charm under test is left to the suite: resources, config and unit count differ for every charm.

## Overriding a step

pytest-bdd picks the matching step definition closest to the test: test module, then `conftest.py` files from the innermost directory outwards, then plugins such as this package. Redefine a sentence in the suite to change its behaviour.

## Versioning

The sentences are the public API: rewording one is a breaking change; adding one is a feature.
