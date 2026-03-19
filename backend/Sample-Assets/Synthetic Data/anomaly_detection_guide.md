# Anomaly Detection Guide — Synthetic Dataset

## A1: Network Timeout Cascade (ATM-GB-0003, 10:00)
- **Sources:** ATM App Log, Kafka Stream, Terminal Handler Log
- **Correlation ID:** `corr-0030-nnet-disc-0001`
- **Detection signals:**
  - ATM App Log: `event_type=NETWORK_DISCONNECT` → `error_code=ERR-0040`
  - ATM App Log: `event_type=TIMEOUT` with `response_time_ms=30000`
  - Kafka: `atm_status=Offline`, `transaction_failure_reason=HOST_UNAVAILABLE`
  - Terminal Handler: `event_type=NETWORK_TIMEOUT` for ATM-GB-0003
- **Expected alert:** ATM offline due to network failure. Cross-source confirmation.

## A2: Cash Cassette Depletion → Out of Service (ATM-GB-0003, 09:00–09:59)
- **Sources:** ATM Hardware Sensor Log, Kafka Stream
- **Detection signals:**
  - Hardware Log: `CASSETTE_LOW` (severity=WARNING) × 2 cassettes
  - Hardware Log: `CASSETTE_EMPTY` (severity=CRITICAL) × 2 cassettes
  - Kafka: `atm_status=Out of Service`, `transaction_failure_reason=CASH_DISPENSE_ERROR`
  - Kafka: `transaction_rate_tps=0.0`, `transaction_success_rate=0.0`
- **Expected alert:** ATM out of service — cash cassettes exhausted. Escalating severity chain.

## A3: JVM Memory Leak → OOM (Terminal Handler, 08:00–09:30)
- **Sources:** Prometheus Metrics, GCP Cloud Metrics, Terminal Handler App Log
- **Detection signals:**
  - Prometheus: `jvm_memory_used_bytes` rising monotonically: 300MB → 1040MB over 90 mins
  - Prometheus: `jvm_gc_pause_seconds_sum` increasing: 0.45s → 24.7s (GC thrashing)
  - Prometheus: `process_cpu_usage` rising to 0.94 (94%)
  - GCP: `container/cpu/usage_time` rising to 94%
  - Terminal Handler Log: `OutOfMemoryError` FATAL event
- **Expected alert:** JVM heap leak detected. GC overhead climbing. OOM imminent.

## A4: Container Restart Loop (Terminal Handler, 09:30–09:34)
- **Sources:** GCP Cloud Metrics, Terminal Handler App Log
- **Detection signals:**
  - GCP: `container/restart_count` = 1, then 2 within 4 minutes
  - Terminal Handler Log: `event_type=STARTUP` repeated 3× (container_id changes each time)
  - Terminal Handler Log: Two `FATAL OutOfMemoryError` events
- **Expected alert:** Container crash loop detected. 2 restarts in under 5 minutes.

## A5: High Response Time Spike + Success Rate Drop (ATM-GB-0001, 09:30)
- **Sources:** Kafka Stream, ATM App Log
- **Correlation IDs:** `corr-0010-xxyy-aabb-1234`, `corr-0011-xyzw-ccdd-5678`
- **Detection signals:**
  - Kafka: `response_time_ms` = 3200ms then 30000ms (normal: ~290ms)
  - Kafka: `transaction_success_rate` drops from 100% to 72% to 50%
  - Kafka: `failure_count` = 8, then 14
  - ATM App Log: `event_type=TIMEOUT` with `error_code=ERR-0012`
- **Expected alert:** ATM-GB-0001 response time 10× above baseline. Success rate critically low.

## A6: OS Memory Pressure → Application Timeout (ATM-GB-0002, 09:45)
- **Sources:** Windows OS Metrics, ATM App Log
- **Detection signals:**
  - Windows OS Metrics: `memory_usage_percent` escalating: 46% → 98.75% over 2 hours
  - Windows OS Metrics: `network_errors` growing: 0 → 22
  - Windows OS Metrics: `cpu_usage_percent` rising to 91.5%
  - ATM App Log: `event_type=TIMEOUT`, `error_detail` contains "ThreadAbortException" / memory pressure
- **Expected alert:** ATM host memory critically high. Application timeout correlated with OS pressure.

## A7: Malformed / Out-of-Order Kafka Events (ATM-GB-0004)
- **Sources:** Kafka Stream, Prometheus Metrics
- **Detection signals:**
  - Kafka offset 4050 has an earlier timestamp than expected (out-of-order)
  - Kafka offset 4051: `atm_status=null`, `transaction_rate_tps=null` (missing required fields)
  - Prometheus CSV row at 09:33:00 contains `metric_value=890iembre` (non-numeric — malformed)
- **Expected alert:** Malformed event ingestion detected. Schema validation failure. Out-of-order sequence.

## Cross-Channel Correlation Opportunities
| Event Window       | Correlated Sources                            | Link Field         |
|--------------------|-----------------------------------------------|--------------------|
| 10:00 ATM-GB-0003 offline | ATM App Log + Kafka + Terminal Handler   | `correlation_id`   |
| 09:30 OOM crash         | Prometheus + GCP + Terminal Handler Log   | `pod_name` / time  |
| 09:45 ATM-GB-0002 timeout | Windows OS Metrics + ATM App Log        | `atm_id` + time    |
| 09:00–09:59 Cassette empty | Hardware Log + Kafka                   | `atm_id` + time    |