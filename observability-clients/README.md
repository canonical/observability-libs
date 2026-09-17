# observability-clients

A Python library of simple HTTP API clients for common Observability stack workloads (Prometheus, Mimir, Loki, Grafana, Tempo, Pyroscope, Alertmanager), useful for integration tests and ad-hoc scripts alike.

## Overview

`observability-clients` provides simple, dataclass-based clients for the HTTP APIs of common Observability software:

| Module | Class | Description |
|---|---|---|
| `observability_clients.api.prometheus` | `Prometheus` | Query metrics, check alert rules, active alerts, and scrape targets |
| `observability_clients.api.mimir` | `Mimir` | Query metrics and check alerts via Mimir's Prometheus-compatible API |
| `observability_clients.api.loki` | `Loki` | Query logs, check labels, label values, and alert rules |
| `observability_clients.api.grafana` | `Grafana` | Check dashboards, datasources, and alert rules |
| `observability_clients.api.tempo` | `Tempo` | Search traces, check tags, and tag values |
| `observability_clients.api.pyroscope` | `Pyroscope` | Query profiles, check profile types, labels, and label values |
| `observability_clients.api.alertmanager` | `Alertmanager` | Check alerts and silences |

Each class exposes:
- **HTTP methods** that return parsed API responses (e.g., `query()`, `get_rules()`)
- **Check methods** that return `bool` (e.g., `has_metric()`, `has_dashboard()`)

All HTTP methods include automatic retries (via `tenacity`) on connection errors and timeouts.

## Installation

```bash
pip install observability-clients
```

## Quick Start

```python
from observability_clients import Prometheus, Loki, Grafana, Tempo

# Check that Prometheus has a specific metric
prom = Prometheus(url="http://localhost:9090")
assert prom.has_metric("up", labels={"job": "my-app"})

# Check that Loki has logs matching a query
loki = Loki(url="http://localhost:3100")
assert loki.has_log_line('{job="my-app"}', pattern="started successfully")

# Check that Grafana has a specific dashboard
grafana = Grafana(url="http://localhost:3000", headers={"Authorization": "Bearer <token>"})
assert grafana.has_dashboard(title="My Dashboard")

# Check that Tempo has traces for a service
tempo = Tempo(url="http://localhost:3200")
assert tempo.has_traces('{ resource.service.name = "my-app" }')
```

## Usage

### Prometheus / Mimir

```python
from observability_clients import Prometheus, Mimir

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
from observability_clients import Loki

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
from observability_clients import Grafana

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

### Tempo

```python
from observability_clients import Tempo

tempo = Tempo(url="http://localhost:3200")

# HTTP methods
traces = tempo.search('{ resource.service.name = "frontend" }')
trace = tempo.get_trace("abc123def456")
tags = tempo.get_tags()
values = tempo.get_tag_values("http.method")

# Check methods
tempo.has_trace("abc123def456")
tempo.has_traces('{ resource.service.name = "frontend" }')
tempo.has_tag("service.name")
tempo.has_tag("service.name", scope="resource")
tempo.has_tag_value("http.method", "GET")
```

### Pyroscope

```python
from observability_clients import Pyroscope

pyroscope = Pyroscope(url="http://localhost:4040")

# HTTP methods
flamegraph = pyroscope.render('process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="myapp"}')
profile_types = pyroscope.get_profile_types()
labels = pyroscope.get_labels()
values = pyroscope.get_label_values("service_name")

# Check methods
pyroscope.has_profile('process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="myapp"}')
pyroscope.has_profile_type("process_cpu:cpu:nanoseconds:cpu:nanoseconds")
pyroscope.has_label("service_name")
pyroscope.has_label_value("service_name", "myapp")
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
