# GEOminate availability

Public checks of the public health endpoints at geominate.com. This repository
contains no application source, customer data, hosting credentials or API keys.

The standard GitHub-hosted runner checks web availability, database readiness
and the background worker every 15 minutes. A failed check is retried twice.
An ongoing outage creates one issue assigned to the owner; later successful
checks record recovery and close that incident. Only bot-owned monitor issues
are managed. Application or infrastructure settings are never changed.

The workflow uses its short-lived repository-local GitHub token for issues only.
It uses no paid runner, cache or uploaded artifacts. Standard public-repository
runner compute is free under GitHub's current billing documentation.

Run the workflow manually with `alert-test` to create a clearly labelled test
issue without stopping or changing the application. Verify the assignment
notification in GitHub and, if enabled in the owner's settings, email. Creating
an issue alone does not prove inbox or email delivery.

Scheduled Actions can be delayed, interrupted, or disabled by GitHub. Public
repository schedules may be disabled after inactivity. This is an initial
pilot monitor, not an uptime SLA or a guarantee of immediate notification.

Local checks: `python3 -m unittest -v test_monitor.py`.
