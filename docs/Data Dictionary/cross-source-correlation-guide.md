# Cross-Source Correlation Guide

## Primary Correlation Keys

| Field            | Type     | Shared By                                                                                 |
|------------------|----------|-------------------------------------------------------------------------------------------|
| `correlation_id` | UUID v4  | ATM App Log, ATM Hardware Log, Terminal Handler App Log, Kafka Metrics Stream             |
| `transaction_id` | UUID v4  | ATM App Log, Terminal Handler App Log, Kafka Metrics Stream                               |
| `atm_id`         | String   | ATM App Log, ATM Hardware Log, Terminal Handler App Log, Kafka Metrics Stream, OS Metrics |
| `timestamp`      | ISO 8601 | All sources — must be monotonically increasing and in UTC                                 |

## Recommended Anomaly Scenarios for Synthetic Data

| Scenario                    | Sources Involved                               | Key Indicators                                                                 |
|-----------------------------|------------------------------------------------|--------------------------------------------------------------------------------|
| Network Timeout Cascade     | ATM App Log → Kafka → Terminal Handler Log     | `event_type=NETWORK_TIMEOUT`, `transaction_failure_reason=NETWORK_TIMEOUT`     |
| Cash Cassette Low → Empty   | ATM Hardware Log → Kafka                       | `CASSETTE_LOW` then `CASSETTE_EMPTY`, `atm_status=Out of Service`             |
| Memory Leak (JVM)           | Prometheus, GCP Metrics                        | `jvm_memory_used_bytes` rising monotonically, eventual GC pauses increasing    |
| Container Restart Loop      | GCP Metrics, Terminal Handler Log              | `restart_count > 0`, `event_type=STARTUP` repeated in short window             |
| High Response Time Spike    | Kafka Metrics, ATM App Log                     | `response_time_ms` > threshold, `transaction_success_rate` drop                |
| OS Memory Pressure (ATM)    | Windows OS Metrics, ATM App Log                | `memory_usage_percent > 90`, followed by `event_type=TIMEOUT`                  |
| Out-of-Order Kafka Events   | Kafka Metrics Stream                           | `timestamp` not monotonic across `kafka_offset` values                         |
| Malformed Log Injection      | Any source                                     | Missing required fields, null values in non-nullable fields, bad timestamp format |