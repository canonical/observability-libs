"""Every sentence in vocabulary.feature must resolve to a shipped step definition."""

import pkgutil
from pathlib import Path

import pytest

import observability_steps

VOCABULARY = Path(__file__).parent / "vocabulary.feature"


def test_every_sentence_has_a_definition(pytester: pytest.Pytester):
    modules = [
        f"observability_steps.{module.name}"
        for module in pkgutil.iter_modules(observability_steps.__path__)
        if not module.name.startswith("_")
    ]
    pytester.makeconftest(f"pytest_plugins = {modules!r}")
    # --generate-missing only checks steps of scenarios bound to a test.
    pytester.makepyfile(f"from pytest_bdd import scenarios\nscenarios({str(VOCABULARY)!r})\n")

    result = pytester.runpytest("--generate-missing", "--feature", str(VOCABULARY))

    assert "is not defined" not in result.stdout.str(), result.stdout.str()
