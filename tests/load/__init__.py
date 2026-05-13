"""TASK-0072: Locust load suite for CopilotoIA.

This package lives outside the default `pytest` collection — Locust files are
not unit tests and only run when explicitly invoked via `locust -f
tests/load/test_journey_load.py` or via the `load-test` GitHub Actions job.

The companion static tests that *do* run in CI live at
`tests/test_load_journey_static.py`.
"""
