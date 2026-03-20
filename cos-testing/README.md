# cos-testing

A Python library for easy interactions with the [COS](https://charmhub.io/topics/canonical-observability-stack) (Canonical Observability Stack) for testing purposes.

## Overview

`cos-testing` provides simple, dataclass-based clients for the HTTP APIs of common Observability software:

| Module | Class | Description |
|---|---|---|
| `cos_testing.api.prometheus` | `Prometheus` | Query metrics, check alert rules, active alerts, and scrape targets |
| `cos_testing.api.mimir` | `Mimir` | Query metrics and check alerts via Mimir's Prometheus-compatible API |
| `cos_testing.api.loki` | `Loki` | Query logs, check labels, label values, and alert rules |
| `cos_testing.api.grafana` | `Grafana` | Check dashboards, datasources, and alert rules |

Each class exposes:
- **HTTP methods** that return parsed API responses (e.g., `query()`, `get_rules()`)
- **Check methods** that return `bool` (e.g., `has_metric()`, `has_dashboard()`)

All HTTP methods include automatic retries (via `tenacity`) on connection errors and timeouts.

## Installation

```bash
pip install cos-testing
```

## Quick Start

```python
from cos_testing import Prometheus, Loki, Grafana

# Check that Prometheus has a specific metric
prom = Prometheus(url="http://localhost:9090")
assert prom.has_metric("up", labels={"job": "my-app"})

# Check that Loki has logs matching a query
loki = Loki(url="http://localhost:3100")
assert loki.has_log_line('{job="my-app"}', pattern="started successfully")

# Check that Grafana has a specific dashboard
grafana = Grafana(url="http://localhost:3000", headers={"Authorization": "Bearer <token>"})
assert grafana.has_dashboard(title="My Dashboard")
```

## Usage

### Prometheus / Mimir

```python
from cos_testing import Prometheus, Mimir

prom = Prometheus(url="http://localhost:9090")

# HTTP methods (return parsed API response)
result = prom.query("up")
rules = prom.get_rules()
alerts = prom.get_alerts()
targets = prom.get_targets()

# Check methods (return bool)
prom.has_metric("up")
prom.has_metric("http_requests_total", labels={"method": "GET"})
prom.has_alert_rule("HighLatency", group="my-group")
prom.has_active_alert("HighLatency")
prom.has_target(job="node-exporter", health="up")

# Mimir has the same interface (different endpoints)
mimir = Mimir(url="http://localhost:8080")
mimir.has_metric("up")
```

### Loki

```python
from cos_testing import Loki

loki = Loki(url="http://localhost:3100")

# HTTP methods
result = loki.query('{job="my-app"}')
labels = loki.get_labels()
values = loki.get_label_values("job")

# Check methods
loki.has_log_line('{job="my-app"}')
loki.has_log_line('{job="my-app"}', pattern=r"error.*timeout")
loki.has_label("job")
loki.has_label_value("job", "my-app")
loki.has_alert_rule("HighErrorRate")
```

### Grafana

```python
from cos_testing import Grafana

grafana = Grafana(
    url="http://localhost:3000",
    headers={"Authorization": "Bearer <token>"},
)

# HTTP methods
dashboards = grafana.search_dashboards(query="My Dashboard")
datasources = grafana.get_datasources()
alert_rules = grafana.get_alert_rules()

# Check methods
grafana.has_dashboard(title="My Dashboard")
grafana.has_dashboard(uid="abc123")
grafana.has_datasource(name="Prometheus")
grafana.has_datasource(type="loki")
grafana.has_alert_rule("HighCPU", group="infra-alerts")
```

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) and [`just`](https://just.systems/) for development:

```bash
# Set up the virtual environment
just venv

# Run all quality checks (format, lint, test)
just check

# Run tests with coverage
just coverage
```
