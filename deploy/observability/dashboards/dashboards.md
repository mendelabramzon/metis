# Operator dashboards

The panels an operator inspects, each backed by a metric from `src/metis_deploy/observability.py`
(scraped from the collector's Prometheus exporter at `otel-collector:9464`). Label sets are bounded
deliberately to avoid cardinality blow-ups — never per-artifact or per-claim.

| Panel | Metric | Labels | What it answers |
|---|---|---|---|
| Model spend | `metis.model.cost_usd` | `task_class`, `provider`, `tier` | What are models costing, by task class? |
| Policy denials | `metis.policy.denials` | `kind`, `sensitivity` | Is restricted data being blocked from cloud providers? |
| Ingestion lag | `metis.ingestion.lag_seconds` | `connector` | How far behind is each source? |
| Parse/extract failures | `metis.ingestion.parse_failures` | `media_type` | Which file types are failing to parse? |
| Job failures | `metis.jobs.failures` | `kind` | Which background jobs are failing? |
| Skill runs | `metis.skills.runs` | `skill`, `outcome` | Are skills succeeding / needing approval / erroring? |

## Tracing

Every unit of work carries a `trace_id` (see `TRACE_ID_FIELD`) that stitches a request across the
gateway and the workers, so a slow query or a failed job can be followed end to end. Drill from a
failed-job panel into its trace by `trace_id`.

These descriptors are intentionally tool-agnostic (Grafana/Perses/etc. import them as panel specs);
the collector config that feeds them is `../otel-collector.yml`.
