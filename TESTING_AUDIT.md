# LAAD Testing Coverage Audit

**Current**: 815 tests (656 backend pytest + 149 frontend vitest + 10 Playwright E2E)
**Target**: ~1,015 tests across 6 layers
**Progress**: ✅ Phase 2 written (+53 new), awaiting CI validation

---

## The Plan

### ✅ Phase 1: Critical Backend Gaps — **IMPLEMENTED** (+58 new, 76 total with pre-existing)

| File | What | Type | Tests | Status |
|------|------|------|-------|--------|
| `backend/tests/test_pubsub_alerts.py` | Redis Pub/Sub alerting | Unit + mock Redis | 7 | ✅ Pre-existing |
| `backend/tests/test_analytics_counters.py` | Analytics helpers (counters, HLL, realtime) | Unit + mock Redis | 11 | ✅ Pre-existing |
| `backend/tests/test_server_routes.py` | Health probes, startup retry, exception handler, CORS | Integration + TestClient | 12 | ⏳ Written — awaiting CI |
| `backend/tests/test_analytics_router_endpoints.py` | Analytics endpoint integration via TestClient | Integration + TestClient | 9 | ⏳ Written — awaiting CI |
| `backend/tests/test_analysis_router_full.py` | `/analysis/detailed` + `/analysis/metrics` endpoints | Integration + TestClient | 5 | ⏳ Written — awaiting CI |
| `backend/tests/test_parsers_edge_cases.py` | 8 parsers × edge cases (malformed, missing, boundary) | Unit + parametrize | 32 | ⏳ Written — awaiting CI |

### ✅ Phase 2: Under-Tested Backend — **IMPLEMENTED** (+53 new, +29 pre-existing analysis)

| File | What | Type | Tests | Status |
|------|------|------|-------|--------|
| `backend/tests/test_anomalies_router_full.py` | Feedback PATCH, 3 grouping modes, 3 sort modes, 6 filters, cache, pagination, auth | Integration | 20 | ✅ New |
| `backend/tests/test_admin_router_full.py` | Ingestion-errors CRUD, cleanup triggers, user create + validation | Integration | 10 | ✅ New |
| `backend/tests/test_cleanup_direct.py` | `batched_delete()`, `batched_delete_all()`, `run_wipe()` — edge cases | Unit + mock conn | 10 | ✅ New |
| `backend/tests/test_write_helper_retry.py` | Retry/backoff, execute_values vs executemany, transient errors | Unit + mock conn | 6 | ✅ New |
| `backend/tests/test_continuous_generator.py` | `emit_tick()`, anomaly cooldown, backfill, producer flush | Unit + mock producer | 7 | ✅ New |
| `backend/tests/test_analysis_logic.py` | A1–A7 functions, `_build_classifier_description()`, `build_detailed_table()`, `time_window()`, `rank_algorithm()` | Unit | 29 | ✅ Pre-existing (comprehensive) |
| `backend/tests/test_anomalies_endpoints.py` | Basic list/filter/resolve/star/feedback | Integration | 3 | ✅ Pre-existing |
| `backend/tests/test_admin_retention_endpoints.py` | Retention GET/PUT, admin-only check, wipe | Integration | 2 | ✅ Pre-existing |
| `backend/tests/test_admin_training_endpoint.py` | ML training route check, method, response model | Unit | 3 | ✅ Pre-existing |
| `backend/tests/test_cleanup.py` | run_cleanup, defaults, batched_delete batches | Integration | 3 | ✅ Pre-existing |

### Phase 3: Frontend Coverage (32 tests, 8h)

| File | Current | Target | Tests |
|------|---------|--------|-------|
| `frontend/src/test/App.test.jsx` | 0% | 85%+ | 4 |
| `frontend/src/test/DiagnosticAssistant.test.jsx` | 21% | 80%+ | 8 |
| `frontend/src/test/AdminSettings.test.jsx` | 34% | 80%+ | 6 |
| `frontend/src/test/AnomalyListPage.test.jsx` | 44% | 80%+ | 6 |
| `frontend/src/test/Analytics.test.jsx` | 52% | 80%+ | 4 |
| `frontend/src/test/AnomalyData.test.jsx` | 59% | 80%+ | 4 |

### Phase 4: Terraform Tests (35 tests, 8h)

| File | What | Tests |
|------|------|-------|
| `terraform/tests/setup.tf` | Shared test infrastructure | — |
| `terraform/tests/vpc_test.tftest.hcl` | VPC module output assertions | 3 |
| `terraform/tests/rds_test.tftest.hcl` | RDS module output assertions | 3 |
| `terraform/tests/ecs_test.tftest.hcl` | ECS module output assertions | 3 |
| `terraform/tests/iam_test.tftest.hcl` | IAM module policy assertions | 3 |
| `terraform/tests/kafka_test.tftest.hcl` | MSK config assertions | 3 |
| `terraform/tests/ecr_test.tftest.hcl` | ECR repo assertions | 2 |
| `terraform/tests/frontend_test.tftest.hcl` | CloudFront/S3 assertions | 3 |
| — | Replace .checkov.baseline with per-finding waivers | 15 rules |

### ✅ Phase 5: E2E + API Contracts — **IMPLEMENTED** (41 tests)

| File | Tool | What | Tests |
|------|------|------|-------|
| `frontend/e2e/auth.spec.js` | Playwright | Login → dashboard loads + invalid creds | 2 |
| `frontend/e2e/anomalies.spec.js` | Playwright | List loads, filter severity, toggle star | 3 |
| `frontend/e2e/diagnostic.spec.js` | Playwright | Chat interface renders, example queries visible | 1 |
| `frontend/e2e/admin.spec.js` | Playwright | Settings page loads with retention + user creation | 1 |
| `frontend/e2e/mobile.spec.js` | Playwright | Mobile + tablet viewport, sidebar collapse | 3 |
| `backend/tests/test_api_contract.py` | pytest + TestClient | Schema validation, non-5xx for all endpoints, response shape | 31 |

**Infrastructure also created:**
- `frontend/playwright.config.js` — Chromium project, 30s timeout, CI retries
- `docker-compose.yml` — `playwright` service (profile: `test`, `mcr.microsoft.com/playwright` image)
- `Makefile` — `test-e2e` (starts full stack) + `test-e2e-quick` (existing stack)
- `.github/workflows/ci.yml` — E2E job (starts Postgres, backend, frontend build, runs Playwright)
- `.gitignore` — Playwright report/results dirs added
- `frontend/package.json` — `test:e2e` script added
- Backend API contract uses `fastapi.testclient.TestClient` (no extra deps needed)

### Phase 6: Load + Security (33 tests, 8h)

| File | Tool | What | Tests |
|------|------|------|-------|
| `backend/tests/stress/test_kafka_throughput.py` | pytest + k6 | 1,000+ msg/s throughput | 2 |
| `backend/tests/stress/test_api_concurrent.py` | pytest + k6 | 100+ concurrent users | 3 |
| `backend/tests/test_security_sql_injection.py` | pytest parametrize | SQLi on all query params | 10 |
| `backend/tests/test_security_auth.py` | pytest | JWT tampering, RBAC escalation, rate-limit abuse | 13 |
| — | CI check + checkov | IaC compliance, no new findings | 5 |

### CI Gating

| Pipeline | Gate |
|----------|------|
| **pytest** | All pass + `--cov-fail-under=80` |
| **vitest** | All pass + `--coverage 80%` |
| **Playwright** | All pass — CI runs on backend + frontend changes |
| **k6** | Thresholds met (nightly + pre-release) |
| **Terraform test** | All modules pass (PR touches `terraform/`) |
| **checkov** | Zero new failures (PR touches `terraform/`) |
| **OpenAPI contract** | All 30+ endpoints match schema — CI-ready |

### Quick Wins (In Priority Order)

1. **`test_pubsub.py`** — 7 unit tests, ~30 min. Zero → ~85%.
2. **`test_analytics_router.py`** — 14 integration tests, ~2h. Zero → fully covered.
3. **`test_parsers_edge_cases.py`** — 24 unit tests, ~1.5h. ~15% → ~70%.
4. **`test_server_routes.py`** — 8 tests, ~1h. Zero → ~75%.
5. **Terraform test per module** — 20 tests, ~4h. Zero → comprehensive.
6. ~~**Playwright E2E** — 10 tests, ~4h. Zero → first E2E coverage.~~ ✅ **Done**
