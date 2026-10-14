"""Every shipped feature file must be runnable with the shipped step definitions alone."""

import pkgutil
from importlib.resources import files

import pytest

from observability_features import steps


def test_every_shipped_step_has_a_definition(pytester: pytest.Pytester):
    modules = [
        f"observability_features.steps.{module.name}"
        for module in pkgutil.iter_modules(steps.__path__)
        if not module.name.startswith("_")
    ]
    features_dir = files("observability_features") / "features"
    pytester.makeconftest(f"pytest_plugins = {modules!r}")
    # --generate-missing only checks steps of scenarios bound to a test.
    pytester.makepyfile(f"from pytest_bdd import scenarios\nscenarios({str(features_dir)!r})\n")

    result = pytester.runpytest("--generate-missing", "--feature", str(features_dir))

    assert "is not defined" not in result.stdout.str(), result.stdout.str()
