"""Test-suite configuration.

Registers ``conftest_e2e`` as a pytest plugin so the journey suite can request
its fixtures (``tenant_factory``, ``e2e_database_url``) by name. The plugin
itself is inert when ``RUN_E2E != 1`` — every fixture short-circuits with
``pytest.skip``.
"""
pytest_plugins = ['tests.conftest_e2e']
