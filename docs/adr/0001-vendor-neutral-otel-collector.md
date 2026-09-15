# 0001 — Instrument tracing vendor-neutrally via OpenTelemetry and an OTel Collector

**Status**: Accepted (2026-09-15) · [Plan](../observability-otel-plan.md)

LAAD's historical monitoring is provider-native (CloudWatch dashboards and log metric filters from the ECS era), and its cloud target has moved before (documented infra history). Locking tracing to one provider would repeat the coupling problem in a new pillar. We instrument every Python service once with OpenTelemetry SDKs and export through an OTel Collector, so the backend is an exporter configuration — Jaeger in dev today, Cloud Trace when GKE lands, ADOT/X-Ray if AWS returns.

## Considered options

- **AWS X-Ray SDK**: rejected — AWS-proprietary, and for this client mix (LangChain, kafka-python, MCP boundaries) no first-party X-Ray SDK story exists; would duplicate work and freeze a vendor in.
- **Direct OTLP exporters from app containers (no collector)**: rejected for now — the collector adds buffering/retries and lets the backend change without touching application containers; the cost is one compose service.
- **OpenTelemetry + collector with Jaeger as dev backend**: **chosen** — one instrumentation path, zero vendor lock, the swap later is a config line.

## Consequences

- Application containers know only OTLP + env vars.
- CloudWatch-era artifacts stay in the repo as historical evidence; nothing is deleted or "ported" — the story is moving forward, not rewriting.
