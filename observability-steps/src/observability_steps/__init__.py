"""observability-steps: shared pytest-bdd step definitions for Observability tests.

Each module is a vocabulary for one domain concept. A test suite registers the modules it
needs as pytest plugins in its top-level ``conftest.py`` and writes its own feature files
with those steps::

    pytest_plugins = ["observability_steps.tls", "observability_steps.logs"]

Steps name the applications they talk about (``the "alertmanager" application``), so
they need nothing from the suite but a ``juju`` fixture (``jubilant.Juju``), e.g. from
``pytest-jubilant``.
"""
