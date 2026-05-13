"""Test-suite configuration.

Registers ``conftest_e2e`` as a pytest plugin so the journey suite can request
its fixtures (``tenant_factory``, ``e2e_database_url``) by name. The plugin
itself is inert when ``RUN_E2E != 1`` — every fixture short-circuits with
``pytest.skip``.

``tests/load/`` contains the Locust suite (TASK-0072); it is invoked by the
`load-test` GitHub Actions job and excluded from default pytest collection so
the unit-test CI does not require ``locust`` to be installed.
"""
pytest_plugins = ['tests.conftest_e2e']
collect_ignore_glob = ['load/*']
