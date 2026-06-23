# LAAD Testing Coverage Audit

**Date**: 2026-06-23
**Backend Tests**: 514 pytest tests across 61 files (incl. 1 stress test)
**Frontend Tests**: 149 vitest tests across 36 files
**Total**: 663 tests

---

## 1. Overall Coverage Assessment

| Area | Coverage | Assessment |
|------|----------|------------|
| Backend — ML Anomaly Detection | ~85% | Good |
| Backend — RAG Pipeline | ~80% | Good |
| Backend — Kafka Infrastructure | ~75% | Good |
| Backend — Live Generator | ~70% | Good |
| Backend — Anomaly Detector (A1–A7 logic) | ~65% | Fair |
| Backend — Auth & Security | ~60% | Fair |
| Backend — Redis | ~70% | Good |
| Backend — Parser Tests | ~15% | **CRITICAL GAP** |
| Backend — API Endpoint Tests | ~40% | **Large Gap** |
| Backend — Admin & Cleanup | ~25% | **Large Gap** |
| Backend — Alerts/PubSub | 0% | **CRITICAL GAP** |
| Backend — Analysis & Analytics | ~30% | **Large Gap** |
| Frontend — Overall | 66.73% statements | Fair |
| Frontend — Core Pages | ~45% | **Large Gap** |
| E2E Tests | 0% | **Missing entirely** |
| Stress/Load Tests | 1 file, 1 test | **Critical Gap** |

---

## 2. Backend Test Distribution

| Category | Files | Tests | Coverage |
|----------|-------|-------|----------|
| RAG Pipeline | 10 | ~108 | ~80% |
| ML Anomaly Detection | 4 | ~98 | ~85% |
| Anomaly/Analysis | 5 | ~80 | ~65% |
| Kafka Infrastructure | 7 | ~64 | ~75% |
| Live Generator | 4 | ~60 | ~70% |
| Redis | 3 | ~29 | ~70% |
| Auth & Security | 4 | ~26 | ~60% |
| Database | 5 | ~26 | ~50% |
| DLQ & Ingestion | 3 | ~21 | ~40% |
| Other | 5 | ~27 | ~30% |
| Admin | 3 | ~8 | ~25% |
| Parsers | 8 | ~9 | ~15% |
| Alerts/PubSub | 1 | 0 | **0%** |
| Server/Startup | 1 | 0 | **0%** |

---

## 3. Frontend Per-File Coverage

| File | Statements | Branches | Functions | Priority |
|------|-----------|----------|-----------|----------|
| `App.jsx` | 0.0% | 100.0% | 0.0% | **HIGH** |
| `DiagnosticAssistant.jsx` | 21.1% | 32.4% | 0.0% | **HIGH** |
| `AdminSettings.jsx` | 34.2% | 23.9% | 34.7% | **HIGH** |
| `AnomalyListPage.jsx` | 44.7% | 38.1% | 29.7% | HIGH |
| `Analytics.jsx` | 52.7% | 55.1% | 24.4% | HIGH |
| `AnomalyData.jsx` | 59.6% | 58.0% | 63.0% | MEDIUM |
| `Sidebar.jsx` | 64.3% | 86.4% | 33.3% | MEDIUM |
| `ui/button.jsx` | 66.7% | 0.0% | 0.0% | MEDIUM |
| `useRAG.jsx` | 75.0% | 50.0% | 100.0% | LOW |
| `AuthProvider.jsx` | 76.9% | 57.1% | 71.4% | LOW |
| `SearchContext.jsx` | 100.0% | 100.0% | 100.0% | — |
| `AnomalyCard.jsx` | 100.0% | 100.0% | 100.0% | — |
| `MarkdownRenderer.jsx` | 98.6% | 97.7% | 98.6% | — |
| `Dashboard.jsx` | 100.0% | 100.0% | 100.0% | — |
| `Completed.jsx` | 100.0% | 100.0% | 100.0% | — |
| `Starred.jsx` | 100.0% | 100.0% | 100.0% | — |
| UI Components (badge, card, input, label, skeleton, switch, toast) | 100.0% | 100.0% | 100.0% | — |

**Frontend average**: 66.73% statements, 54.55% branches, 55.1% functions, 69.43% lines

---

## 4. Critical Gaps (Zero or Near-Zero Coverage)

### 4.1 `backend/src/alerts/pubsub.py` — 0 tests

The entire Redis Pub/Sub alerting system has zero tests.

| Function | Lines | What It Does |
|----------|-------|-------------|
| `publish_anomaly()` | 31–55 | Publishes to Redis channel + increments ATM ranked set |
| `get_top_anomalous_atms()` | 58–73 | Reads top N from Redis sorted set |

**Risk**: Silent failure breaks real-time anomaly streaming to the dashboard.

### 4.2 `backend/src/api/server.py` — 0 tests

| Function/Route | Lines | What It Does |
|----------------|-------|-------------|
| `_ensure_db_initialized()` | 36–54 | Retry logic (3 attempts, 2s backoff) |
| `lifespan()` | 58–74 | Scheduler startup/shutdown |
| `_check_and_retrain_on_startup()` | 77–97 | Model validation, retrain if corrupted |
| `_do_retrain()` | 100–109 | Runs training pipeline |
| `GET /health` | 123–126 | Liveness probe |
| `GET /health/ready` | 129–142 | Readiness probe with DB check |
| `global_exception_handler()` | 145–152 | Unhandled exception → JSON |
| CORS config | 114–120 | CORS origins parsing |

### 4.3 `backend/src/analytics/analytics_router.py` — 0 endpoint tests

| Route | Method | What It Does |
|-------|--------|-------------|
| `/api/analytics/events` | GET | Time-bucketed event counts per source |
| `/api/analytics/metrics` | GET | Time-bucketed metric averages |
| `/api/analytics/metrics/list` | GET | Unique metric names |
| `/api/analytics/stats/realtime` | GET | Redis + DB fallback stats |
| `/api/analytics/entities` | GET | All ATM/server entities |
| `increment_event_counter()` | — | Redis incr with 7d expiry |
| `increment_anomaly_counter()` | — | Redis zincrby with 7d expiry |
| `track_unique_atm()` | — | HyperLogLog pfadd |
| `get_unique_atm_count()` | — | HyperLogLog pfcount |

### 4.4 `backend/src/analysis/analysis.py` — 851 lines, ~30% coverage

| Function | Lines | Tested? |
|----------|-------|---------|
| `rank_algorithm()` | 107–206 | Tested |
| `get_reference_now()` | 209–223 | Not tested |
| `get_age_score()` | 227–257 | Tested |
| `_to_datetime()` | 96–105 | Tested |
| `time_window()` | 402–413 | **Not tested** |
| `_build_classifier_description()` | 79–93 | **Not tested** |
| `A1()` | 261–284 | **Not tested** |
| `A2()` | 287–305 | **Not tested** |
| `A3()` | 308–324 | **Not tested** |
| `A4()` | 327–344 | **Not tested** |
| `A5()` | 347–362 | **Not tested** |
| `A6()` | 365–380 | **Not tested** |
| `A7()` | 383–400 | **Not tested** |
| `build_detailed_table()` | 419–824 | **Not tested (0 direct tests)** |
| `query()` | 828–839 | **Not tested** |
| `main()` | 843–851 | **Not tested** |

### 4.5 Parser Tests — 8 files, 9 tests total (~15% coverage)

| Parser | Tests | Edge Cases? |
|--------|-------|-------------|
| `atm_app.py` | 1 | No |
| `base_parser.py` | 2 | Partial |
| `gcp_cloud_metrics.py` | 1 | No |
| `hardware_sensor.py` | 1 | No |
| `kafka_metrics.py` | 1 | No |
| `prometheus.py` | 1 | No |
| `terminal_handler.py` | 1 | No |
| `windows_os.py` | 1 | No |

Each parser has only a single happy-path integration test. Malformed input, missing fields, encoding issues, boundary values — all untested.

---

## 5. Large Gaps (Under-Tested Modules)

### 5.1 API Endpoint Tests (~40%)

| Router | Endpoints | Tested | Untested |
|--------|-----------|--------|----------|
| `anomalies_router.py` | 4 | 3 endpoints (partial) | Feedback PATCH, cache, grouping modes, filters |
| `admin_router.py` | 7 | 3 endpoints | ingestion-errors CRUD, users create, cleanup/run |
| `analysis_router.py` | 2 | 1 endpoint (partial) | `/analysis/metrics` |
| `analytics_router.py` | 5 | 0 | All 5 endpoints |

### 5.2 `backend/src/anomalies/anomalies_router.py` (503 lines)

**Tested**:
- Basic list + severity filter
- `group_by=atm` mode
- `star` toggle
- `resolve` toggle

**Not tested**:
- `group_by=atm_anomaly` mode
- `group_by=title_atm` mode
- `entity_type` filter (atm vs server)
- `detection_source` filter (ML_ENSEMBLE, ZSCORE, HEURISTIC)
- `sort_by` modes (detected_at, severity, score)
- `is_starred` filter
- `is_active` filter
- `from_date` / `to_date` filters
- Caching functions (`_get_cache_key`, `_get_cached_result`, `_cache_result`, `_invalidate_anomaly_cache`)
- `setFeedback` endpoint

### 5.3 `backend/src/admin/` (~25%)

**Tested**: `GET /retention`, `PUT /retention`, `POST /cleanup/wipe`
**Not tested**: `GET /ingestion-errors`, `DELETE /ingestion-errors`, `POST /cleanup/run`, `POST /users`

### 5.4 `backend/src/ingestion/write_helper.py`

- Retry/backoff logic — **not tested**
- `execute_values` vs `executemany` code path — **not tested**
- Transient error handling (deadlock, serialization, lock errors) — **not tested**
- Exception handling in rollback — **not tested**

### 5.5 `backend/generator/continuous_generator.py`

- `emit_tick()` — **not directly tested**
- `backfill()` error handling — **not tested**
- `main()` — **not tested**
- Signal handlers (SIGTERM/SIGINT) — **not tested**

### 5.6 `backend/src/anomaly_detection/anomaly_detector.py`

- A1–A7 detection logic — **tested**
- `detect_anomalies_from_window()` — **tested** (basic dedup)
- `AnomalyDetector.save_anomalies()` — **not tested**
- `AnomalyDetector.query()` — **not tested**
- `AnomalyDetector.main()` — **not tested**
- `_ingestion_errors_in_window()` — **not directly tested** (tested indirectly via integration)
- `_as_float()` / `_payload_get()` — **tested**

### 5.7 `backend/src/database/`

- `config.py` — partially tested
- `connection.py` — **partially tested**
- `init_db.py` — **tested** (seed, schema)

---

## 6. Missing Test Archetypes

### 6.1 E2E Tests — 0%

No Playwright, Cypress, or browser-level tests exist. Critical user journeys never tested end to end:
- Login → Dashboard → Anomaly List → Anomaly Details
- Login → Diagnostic Assistant → RAG query
- Admin → Retention config → Cleanup
- Real-time anomaly streaming via SSE

### 6.2 Load / Stress Tests — 1 file, 1 test

Only `test_write_helper_locking_collision.py` exists. Missing:
- Kafka consumer under high throughput
- Database under concurrent writes
- API under concurrent requests (rate limiting)
- Continuous generator under long-duration runs
- Memory profiling under sustained load

### 6.3 Security Tests

- SQL injection on query parameters — **not tested**
- JWT tampering / signature bypass — **not tested**
- Role escalation (user → admin) — **not tested**
- Rate-limit bypass — **not tested**
- XSS in anomaly data — **not tested**
- CSRF protection — **not tested**

### 6.4 API Contract Tests

- OpenAPI spec compliance — **not validated**
- Response schema validation — **not tested**
- Error response format consistency — **not tested**

---

## 7. Detailed Test Implementation Plan

### Tier 1: Critical (Do First)

| # | What | Why | Type | Est. Tests |
|---|------|-----|------|------------|
| 1 | `pubsub.py`: `publish_anomaly()` success, Redis unavailable, exception | Zero coverage on real-time alerting | Unit (mocked Redis) | 4 |
| 2 | `pubsub.py`: `get_top_anomalous_atms()` success, empty, Redis unavailable | Zero coverage | Unit (mocked Redis) | 3 |
| 3 | `server.py`: `_ensure_db_initialized()` retry on failure, immediate success | Startup reliability | Unit (patched init_db) | 3 |
| 4 | `server.py`: `_check_and_retrain_on_startup()` models exist, corrupted, missing | Model validation on boot | Unit (patched joblib) | 3 |
| 5 | `server.py`: `lifespan()` scheduler add/start/shutdown | Scheduler lifecycle | Integration | 2 |
| 6 | `server.py`: `GET /health`, `GET /health/ready` | Liveness/readiness probes | Integration | 2 |
| 7 | `server.py`: global exception handler | Unhandled exception → JSON | Integration | 1 |
| 8 | `analytics_router.py`: `GET /api/analytics/events` all params, empty results | Zero endpoint coverage | Integration (TestClient + DB) | 4 |
| 9 | `analytics_router.py`: `GET /api/analytics/metrics` all params, empty results | Zero endpoint coverage | Integration | 4 |
| 10 | `analytics_router.py`: `GET /api/analytics/metrics/list` | Zero endpoint coverage | Integration | 1 |
| 11 | `analytics_router.py`: `GET /api/analytics/stats/realtime` Redis + DB fallback | Zero endpoint coverage | Integration + mocked Redis | 4 |
| 12 | `analytics_router.py`: `GET /api/analytics/entities` | Zero endpoint coverage | Integration | 1 |
| 13 | `analytics_router.py`: helper functions (increment/ track/ get) | No direct tests | Unit (mocked Redis) | 4 |
| 14 | `analysis_router.py`: `GET /analysis/metrics` all params | No endpoint test | Integration | 4 |
| 15 | Parser edge cases: malformed input, missing fields, special chars | Only 1 happy-path test each | Unit | 16 |
| 16 | Parser boundary values: empty input, whitespace-only, unicode | Edge cases | Unit | 8 |

**Tier 1 total: ~58 tests**

### Tier 2: High Priority

| # | What | Why | Type | Est. Tests |
|---|------|-----|------|------------|
| 17 | `anomalies_router.py`: PATCH feedback (LIKE, DISLIKE, invalid, not found) | Untested endpoint | Integration | 4 |
| 18 | `anomalies_router.py`: group_by=atm_anomaly mode | Untested grouping | Integration | 2 |
| 19 | `anomalies_router.py`: group_by=title_atm mode | Untested grouping | Integration | 2 |
| 20 | `anomalies_router.py`: entity_type filter (atm, server) | Untested filter | Integration | 2 |
| 21 | `anomalies_router.py`: detection_source filter (ML_ENSEMBLE, ZSCORE, HEURISTIC) | Untested filter | Integration | 3 |
| 22 | `anomalies_router.py`: sort_by modes (detected_at, severity, score) | Untested sort | Integration | 3 |
| 23 | `anomalies_router.py`: cache functions | No direct tests | Unit (mocked Redis) | 8 |
| 24 | `admin_router.py`: GET /admin/ingestion-errors | Untested | Integration | 2 |
| 25 | `admin_router.py`: DELETE /admin/ingestion-errors | Untested | Integration | 2 |
| 26 | `admin_router.py`: POST /admin/cleanup/run | Untested | Integration | 1 |
| 27 | `admin_router.py`: POST /admin/users (create, duplicate, invalid role) | Untested | Integration | 3 |
| 28 | `cleanup.py`: `batched_delete()` each table, empty table, invalid table | No direct tests | Unit (mocked conn) | 5 |
| 29 | `cleanup.py`: `batched_delete_all()` | No direct tests | Unit (mocked conn) | 3 |
| 30 | `write_helper.py`: retry/backoff on transient errors, max retries exhausted | Partial coverage | Unit (mocked conn) | 4 |
| 31 | `write_helper.py`: execute_values vs executemany code path | Untested branch | Unit | 2 |
| 32 | `analysis.py`: A1–A7 detailed analysis functions | Zero coverage | Unit | 7 |
| 33 | `analysis.py`: `_build_classifier_description()` all 5 types + fallback | Zero coverage | Unit | 6 |
| 34 | `analysis.py`: `build_detailed_table()` all 8 branches | No direct tests | Unit | 8 |
| 35 | `analysis.py`: `time_window()`, `get_reference_now()` | Not tested | Unit | 3 |
| 36 | `continuous_generator.py`: `emit_tick()` emitters error handling | Not directly tested | Unit (mocked producer) | 3 |
| 37 | `continuous_generator.py`: `backfill()` shutdown, error handling | Not tested | Unit | 3 |
| 38 | `anomaly_detector.py`: `save_anomalies()` DB insert path | No tests | Integration | 3 |
| 39 | `anomaly_detector.py`: `AnomalyDetector` class methods | Not tested | Unit | 3 |

**Tier 2 total: ~62 tests**

### Tier 3: Frontend

| # | What | Why | Type | Est. Tests |
|---|------|-----|------|------------|
| 40 | `App.jsx`: renders routes, redirects unauthenticated | 0% coverage | Component | 4 |
| 41 | `DiagnosticAssistant.jsx`: query submission, results display, loading/error | 21% coverage | Component | 8 |
| 42 | `AdminSettings.jsx`: tab navigation, form submission, validation | 34% coverage | Component | 6 |
| 43 | `AnomalyListPage.jsx`: filtering, pagination, grouping display | 44% coverage | Component | 6 |
| 44 | `Analytics.jsx`: chart rendering, time range selection, empty state | 52% coverage | Component | 4 |
| 45 | `AnomalyData.jsx`: detail rendering, resolve/star/feedback actions | 59% coverage | Component | 4 |

**Tier 3 total: ~32 tests**

### Tier 4: Test Archetypes (New Types)

| # | What | Why | Tool | Est. Tests |
|---|------|-----|------|------------|
| 46 | E2E: Login → Dashboard loads anomalies | Full flow never tested | Playwright | 2 |
| 47 | E2E: Anomaly list → filter → view details → resolve/star | Critical user journey | Playwright | 2 |
| 48 | E2E: Diagnostic Assistant → query → see RAG answer | AI feature flow | Playwright | 1 |
| 49 | E2E: Admin → retention → cleanup | Admin flow | Playwright | 1 |
| 50 | Load: Kafka consumer throughput (1000s of messages) | Production stress | Custom (locust/k6) | 2 |
| 51 | Load: API under concurrent requests (100+ simultaneous) | Bottleneck detection | k6 | 2 |
| 52 | Load: Continuous generator extended run (hours) | Memory/resource leak | Custom | 1 |
| 53 | Security: SQL injection on all GET query params | Input validation | Pytest + parametrize | 10 |
| 54 | Security: JWT tampering with expired/invalid tokens | Auth robustness | Integration | 5 |
| 55 | Security: Role escalation — user tries admin endpoints | Authorization | Integration | 4 |
| 56 | Security: Rate-limit under rapid-fire requests | DoS protection | Integration | 3 |
| 57 | API Contract: OpenAPI spec response validation | Schema compliance | Pytest + openapi-core | 30 |

**Tier 4 total: ~63 tests**

---

## 8. Summary

| Tier | What | Tests | Est. Hours | Status |
|------|------|-------|------------|--------|
| Tier 1 | Critical backend gaps (pubsub, server, analytics, parsers) | ~58 | 8–12h | 🟥 Needs work |
| Tier 2 | High-priority backend modules (routers, cleanup, analysis) | ~62 | 10–14h | 🟧 Needs work |
| Tier 3 | Frontend components with <60% coverage | ~32 | 6–8h | 🟨 Needs work |
| Tier 4 | New test archetypes (E2E, load, security, contract) | ~63 | 12–18h | ⬜ Missing |
| **Total** | | **~215** | **36–52h** | |

**After completion**: ~663 → ~878 tests, Backend coverage ~85%+, Frontend ~80%+

### Quick Wins (Do First)

1. **`pubsub.py`** — 7 unit tests, ~30 min. Zero coverage → ~85%.
2. **`analytics_router.py`** — 14 integration tests, ~2h. Zero endpoint coverage → ~70%.
3. **Parser edge cases** — 24 unit tests, ~1.5h. ~15% → ~70%.
4. **`server.py`** — 8 tests, ~1h. Zero coverage → ~75%.
