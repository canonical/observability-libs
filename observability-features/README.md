# observability-features

Shared Gherkin feature files and their default [pytest-bdd](https://pytest-bdd.readthedocs.io/) step definitions for behaviours common to Observability charms (TLS, log forwarding, ...).

> Spike for TAP-1149: evaluates shipping feature files and steps as one pip-installable package.

## Shipped features

| Feature file | Step module | Collaborators deployed |
|---|---|---|
| `tls.feature` | `observability_features.steps.tls` | `self-signed-certificates` as `ca` |
| `log_forwarding.feature` | `observability_features.steps.log_forwarding` | `loki-k8s` as `loki` |

Every feature also needs `observability_features.steps.deployment`.

## Usage

1. Add `observability-features` to the charm's test dependencies.
2. In the integration suite's top-level `conftest.py`, register the step modules and describe the charm under test:

   ```python
   import pytest
   from observability_features import CharmUnderTest

   pytest_plugins = [
       "observability_features.steps.deployment",
       "observability_features.steps.tls",
   ]


   @pytest.fixture(scope="session")
   def charm_under_test(charm_path) -> CharmUnderTest:
       return CharmUnderTest(app="my-app", charm=str(charm_path), workload_port=8080)
   ```

   The steps also need a `juju` fixture (`jubilant.Juju`), e.g. from `pytest-jubilant`.

3. Load the scenarios from a test module:

   ```python
   from observability_features import feature
   from pytest_bdd import scenarios

   scenarios(feature("tls.feature"))
   ```

## Overriding a step

pytest-bdd picks the matching step definition closest to the test: test module, then `conftest.py` files from the innermost directory outwards, then plugins such as this package. To change how a step behaves for one charm, redefine a step whose parser matches the same text in the charm's `conftest.py` or test module.

## Charm-specific scenarios

Shipped feature files cannot be extended in place. Put charm-specific scenarios in a local feature file and load both from the same test module; local scenarios can reuse the shipped steps:

```python
scenarios(feature("tls.feature"), "features/tls.feature")
```

## Versioning

Feature files are part of the public API: renaming or rewording a step, or adding a scenario that needs a new contract field, is a breaking change.
